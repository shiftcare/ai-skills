import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlsplit

from skills_ref.errors import ParseError
from skills_ref.parser import find_skill_md, parse_frontmatter
from skills_ref.validator import validate as validate_skill

SKILLS_ROOT = Path(__file__).resolve().parents[1] / "skills"
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


def validate_repository(skills_root: Path = SKILLS_ROOT) -> list[str]:
    if not skills_root.is_dir():
        return [f"Missing skills directory: {skills_root}"]

    skill_dirs = sorted(path for path in skills_root.iterdir() if path.is_dir())
    if not skill_dirs:
        return [f"No skills found in {skills_root}"]

    errors = []
    names: dict[str, list[str]] = {}
    for skill_dir in skill_dirs:
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

        errors.extend(
            f"{skill_dir.name}: {error}"
            for error in validate_compatibility_check(body, skill_dir)
        )

        errors.extend(validate_local_references(skill_dir, skills_root))

    for name, folders in names.items():
        if len(folders) > 1:
            errors.append(f"duplicate skill name '{name}': {', '.join(folders)}")

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
