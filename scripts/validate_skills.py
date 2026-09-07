import re
import sys
import unicodedata
from datetime import date
from pathlib import Path
from urllib.parse import unquote, urlsplit

import strictyaml
from skills_ref.errors import ParseError
from skills_ref.parser import find_skill_md, parse_frontmatter
from skills_ref.validator import validate as validate_skill

SKILLS_ROOT = Path(__file__).resolve().parents[1] / "skills"
COMPATIBILITY_MANIFEST = SKILLS_ROOT.parent / "public_ai_skills.yml"
SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
MARKDOWN_LINK = re.compile(r"!?\[[^]\n]*\]\(\s*(?:<([^>\n]+)>|([^)\s]+))")
REFERENCE_LINK = re.compile(
    r"^[ \t]{0,3}\[[^]\n]+\]:\s*(?:<([^>\n]+)>|(\S+))", re.MULTILINE
)
RESOURCE_PATH = re.compile(
    r"(?<![\w./-])((?:assets|references|scripts)/[A-Za-z0-9][A-Za-z0-9._/@%+~-]*)"
)
INLINE_CODE = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")
UPDATE_COMMAND = re.compile(r"\bnpx\s+skills\s+update\b")
COMPATIBILITY_TEMPLATE = Path(__file__).with_name("compatibility_check.md")
CORE_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def referenced_paths(text: str) -> tuple[set[str], set[str]]:
    links = {
        match.group(1) or match.group(2)
        for pattern in (MARKDOWN_LINK, REFERENCE_LINK)
        for match in pattern.finditer(text)
    }
    prose = MARKDOWN_LINK.sub("", REFERENCE_LINK.sub("", text))
    resources = {
        match.group(1).rstrip(".,;:") for match in RESOURCE_PATH.finditer(prose)
    }
    return links, resources


def validate_local_references(skill_dir: Path, skills_root: Path) -> list[str]:
    errors = []
    skill_root = skill_dir.resolve()

    for markdown in skill_dir.rglob("*.md"):
        try:
            text = markdown.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            errors.append(f"{markdown.relative_to(skills_root)}: cannot read: {error}")
            continue

        links, resources = referenced_paths(text)
        targets = {(target, markdown.parent) for target in links}
        targets.update((target, skill_dir) for target in resources)
        for target, base in sorted(targets, key=lambda item: item[0]):
            try:
                parsed = urlsplit(target)
            except ValueError:
                errors.append(
                    f"{markdown.relative_to(skills_root)}: invalid reference: {target}"
                )
                continue
            if parsed.scheme or target.startswith("//"):
                if parsed.scheme in {"http", "https", "mailto"}:
                    continue
                errors.append(
                    f"{markdown.relative_to(skills_root)}: invalid reference: {target}"
                )
                continue
            if target.startswith("#"):
                continue

            try:
                referenced = (base / unquote(parsed.path)).resolve()
            except (OSError, RuntimeError, ValueError):
                errors.append(
                    f"{markdown.relative_to(skills_root)}: invalid reference: {target}"
                )
                continue
            try:
                referenced.relative_to(skill_root)
            except ValueError:
                errors.append(
                    f"{markdown.relative_to(skills_root)}: local reference escapes skill: {target}"
                )
                continue
            if not referenced.exists():
                errors.append(
                    f"{markdown.relative_to(skills_root)}: missing local reference: {target}"
                )

        errors.extend(validate_update_commands(text, skill_dir, markdown, skills_root))

    return errors


def validate_update_commands(
    body: str, skill_dir: Path, source: Path, skills_root: Path
) -> list[str]:
    errors = []
    literal_command = f"npx skills update {skill_dir.name}"
    location = source.relative_to(skills_root)
    for line in body.splitlines():
        inline_commands = INLINE_CODE.findall(line)
        for command in inline_commands:
            if UPDATE_COMMAND.search(command) and command.strip() != literal_command:
                errors.append(
                    f"{location}: update command must be the literal "
                    f"'{literal_command}'"
                )

        without_inline_code = INLINE_CODE.sub("", line).strip()
        without_inline_code = re.sub(r"^(?:[-*+>]|\d+\.)\s+", "", without_inline_code)
        if (
            UPDATE_COMMAND.search(without_inline_code)
            and without_inline_code != literal_command
        ):
            errors.append(
                f"{location}: update command must be the literal '{literal_command}'"
            )
    return errors


def validate_compatibility_check(body: str, skill_dir: Path) -> list[str]:
    required = COMPATIBILITY_TEMPLATE.read_text(encoding="utf-8").format(
        skill=skill_dir.name
    ).strip()
    if required in body:
        return []
    return ["compatibility check does not match scripts/compatibility_check.md"]


def validate_compatibility_manifest(
    manifest_path: Path, skill_versions: dict[str, str]
) -> list[str]:
    try:
        manifest = strictyaml.load(manifest_path.read_text(encoding="utf-8")).data
    except FileNotFoundError:
        return [f"Missing compatibility manifest: {manifest_path}"]
    except (strictyaml.YAMLError, OSError, UnicodeError) as error:
        return [f"Cannot read compatibility manifest: {error}"]

    shared = manifest.get("shared") if isinstance(manifest, dict) else None
    if not isinstance(shared, dict) or not isinstance(shared.get("skills"), dict):
        return ["public_ai_skills.yml: shared.skills must be a mapping"]

    errors = []
    entries = shared["skills"]
    for name in skill_versions:
        if name not in entries:
            errors.append(f"{name}: missing from public_ai_skills.yml")

    for name, entry in entries.items():
        if not isinstance(name, str) or not isinstance(entry, dict):
            errors.append(f"public_ai_skills.yml: each skill must map to a mapping")
            continue

        retired_on = entry.get("retired_on")
        if retired_on is not None:
            try:
                if not isinstance(retired_on, str) or not re.fullmatch(
                    r"\d{4}-\d{2}-\d{2}", retired_on
                ):
                    raise ValueError
                date.fromisoformat(retired_on)
            except ValueError:
                errors.append(f"{name}: retired_on must be a valid YYYY-MM-DD date")
            continue

        if name not in skill_versions:
            errors.append(f"{name}: active manifest entry has no skill directory")

        minimum = entry.get("minimum_skill_version")
        latest = entry.get("latest_skill_version")
        for field, value in (
            ("minimum_skill_version", minimum),
            ("latest_skill_version", latest),
        ):
            if not isinstance(value, str) or not CORE_SEMVER.fullmatch(value):
                errors.append(f"{name}: {field} must be a MAJOR.MINOR.PATCH version")

        if not all(
            isinstance(value, str) and CORE_SEMVER.fullmatch(value)
            for value in (minimum, latest)
        ):
            continue
        if tuple(map(int, minimum.split("."))) > tuple(map(int, latest.split("."))):
            errors.append(
                f"{name}: minimum_skill_version {minimum} is above "
                f"latest_skill_version {latest}"
            )
        if name in skill_versions and latest != skill_versions[name]:
            errors.append(
                f"{name}: latest_skill_version {latest} does not match "
                f"metadata.version {skill_versions[name]}"
            )

    return errors


def validate_repository(
    skills_root: Path = SKILLS_ROOT, manifest_path: Path | None = None
) -> list[str]:
    if not skills_root.is_dir():
        return [f"Missing skills directory: {skills_root}"]

    skill_dirs = sorted(path for path in skills_root.iterdir() if path.is_dir())
    if not skill_dirs:
        return [f"No skills found in {skills_root}"]

    errors = []
    names: dict[str, list[str]] = {}
    skill_versions = {}
    for skill_dir in skill_dirs:
        if not skill_dir.name.startswith("shiftcare-"):
            errors.append(
                f"{skill_dir.name}: skill name must start with 'shiftcare-'"
            )
        try:
            errors.extend(
                f"{skill_dir.name}: {error}" for error in validate_skill(skill_dir)
            )
        except (OSError, UnicodeError) as error:
            errors.append(f"{skill_dir.name}: cannot read SKILL.md: {error}")
            continue

        skill_md = find_skill_md(skill_dir)
        if skill_md is None:
            continue
        try:
            metadata, body = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
        except (ParseError, OSError, UnicodeError):
            continue

        name = metadata.get("name")
        if isinstance(name, str):
            normalized_name = unicodedata.normalize("NFKC", name)
            names.setdefault(normalized_name, []).append(skill_dir.name)

        custom_metadata = metadata.get("metadata")
        version = (
            custom_metadata.get("version")
            if isinstance(custom_metadata, dict)
            else None
        )
        if not isinstance(version, str) or not SEMVER.fullmatch(version):
            errors.append(
                f"{skill_dir.name}: metadata.version must be a valid SemVer string"
            )
        else:
            skill_versions[skill_dir.name] = version

        errors.extend(
            f"{skill_dir.name}: {error}"
            for error in validate_compatibility_check(body, skill_dir)
        )

        errors.extend(validate_local_references(skill_dir, skills_root))

    for name, folders in names.items():
        if len(folders) > 1:
            errors.append(f"duplicate skill name '{name}': {', '.join(folders)}")

    errors.extend(
        validate_compatibility_manifest(
            manifest_path or skills_root.parent / COMPATIBILITY_MANIFEST.name,
            skill_versions,
        )
    )

    return errors


def main() -> int:
    errors = validate_repository()
    if errors:
        print("Skill validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(
        f"Valid skills: {len([path for path in SKILLS_ROOT.iterdir() if path.is_dir()])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
