"""Content hashes that decide which results are comparable.

Stamped into every result at collection time, from the live working tree so
uncommitted edits count. `report.py` pools results only within a scenario hash,
and treats a mixed skill hash as a before/after comparison rather than an error.

These replace `EVAL_REPEATS`-as-identity: occurrence is derived at report time by
zipping a group's arms, so a later run appends samples instead of colliding with
the first run's `repeat 1`.
"""

import ast
import hashlib
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
NO_SKILL = "none"


def suites(directory=Path(__file__).parent):
    """Discover scenario suite names and skills without importing their modules."""
    discovered = {}
    for path in sorted(Path(directory).glob("test_*.py")):
        constants = {}
        tree = ast.parse(path.read_text(), filename=str(path))
        for statement in tree.body:
            if not isinstance(statement, ast.Assign):
                continue
            for target in statement.targets:
                if isinstance(target, ast.Name) and target.id in {"SUITE", "SKILL"}:
                    value = ast.literal_eval(statement.value)
                    if isinstance(value, str):
                        constants[target.id] = value
        if constants.keys() >= {"SUITE", "SKILL"}:
            suite = constants["SUITE"]
            if suite in discovered:
                raise ValueError(f"Duplicate SUITE {suite!r}: {path}")
            discovered[suite] = {"file": path, "skill": constants["SKILL"]}
    return discovered


def directory_hash(directory):
    """Hash a directory's file contents, sorted by relative path.

    One file today (`SKILL.md`), so the walk costs nothing, but it survives a
    second file being added to a skill.
    """
    digest = hashlib.sha256()
    for path in sorted(path for path in directory.rglob("*") if path.is_file()):
        digest.update(path.relative_to(directory).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:12]


def skill_hash(skill):
    """Hash an installed skill, or NO_SKILL for the arm that has none.

    Forcing a real hash onto the no-skill arm would split every pair, since the
    two arms would never share an identity.
    """
    if not skill:
        return NO_SKILL
    return directory_hash(PROJECT_ROOT / "skills" / skill)


def cases_hash(path):
    """Hash a scenario module's CASES list.

    Parsed rather than imported so hashing a suite does not execute it, and
    canonicalised so formatting changes alone do not invalidate older results.
    Changes when a prompt, expected tool, or rubric changes — exactly when older
    results stop being comparable.
    """
    path = Path(path)
    tree = ast.parse(path.read_text(), filename=str(path))
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "CASES"
            for target in statement.targets
        ):
            cases = ast.literal_eval(statement.value)
            canonical = json.dumps(
                cases, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            )
            return hashlib.sha256(canonical.encode()).hexdigest()[:12]
    raise ValueError(f"CASES not found in {path}")
