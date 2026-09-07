import tempfile
import unittest
from pathlib import Path

from scripts.validate_skills import COMPATIBILITY_TEMPLATE, validate_repository


class ValidateSkillsTest(unittest.TestCase):
    def test_compatibility_check_allows_servers_without_the_tool(self):
        self.assertIn(
            "If `check_skill_compatibility` is not available, warn the user that "
            "compatibility could not be checked and continue.",
            COMPATIBILITY_TEMPLATE.read_text(),
        )

    def test_repository_policy_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            skills = repository / "skills"
            self.assertIn(
                "Missing skills directory", validate_repository(skills / "missing")[0]
            )
            skills.mkdir()
            self.assertIn("No skills found", validate_repository(skills)[0])

            valid = skills / "valid-skill"
            (valid / "references").mkdir(parents=True)
            (valid / "references" / "guide.md").write_text(
                "[Sibling][sibling]\n\n[sibling]: sibling.md\n"
            )
            (valid / "references" / "sibling.md").write_text("# Sibling\n")
            (valid / "SKILL.md").write_text(
                """---
name: valid-skill
description: A valid test skill.
metadata:
  version: "1.2.3"
---
See [the guide](references/guide.md).
"""
                + COMPATIBILITY_TEMPLATE.read_text().format(skill="valid-skill")
            )
            (repository / "public_ai_skills.yml").write_text(
                """shared:
  skills:
    valid-skill:
      minimum_skill_version: "1.0.0"
      latest_skill_version: "1.2.3"
"""
            )
            self.assertEqual(validate_repository(skills), [])

            (valid / "SKILL.md").write_text(
                (valid / "SKILL.md")
                .read_text()
                .replace("stop and warn", "stop and tell")
            )
            self.assertIn(
                "compatibility check does not match scripts/compatibility_check.md",
                "\n".join(validate_repository(skills)),
            )

            unsafe = skills / "unsafe-skill"
            unsafe.mkdir()
            (unsafe / "SKILL.md").write_text(
                """---
name: unsafe-skill
description: An invalid test skill.
metadata:
  version: "1.0"
---
See [missing][missing], [bad](http://[), [file](file:///etc/passwd), or
[nul](references/%00.md). Avoid [protocol-relative](//example.com/path).

[missing]: references/also-missing.md

Run scripts/missing.py, then `npx skills update another-skill`.
"""
            )
            (unsafe / "references").mkdir()
            (unsafe / "references" / "commands.md").write_text(
                "Run `npx skills update ${MCP_OUTPUT}`.\n"
            )
            duplicate = skills / "duplicate-folder"
            duplicate.mkdir()
            (duplicate / "SKILL.md").write_text(
                """---
name: valid-skill
description: A duplicate test skill.
metadata:
  version: "1.0.0"
---
"""
            )
            malformed = skills / "malformed"
            malformed.mkdir()
            (malformed / "SKILL.md").write_text(
                """---
name: malformed
name: malformed
description: Duplicate YAML keys are invalid.
---
"""
            )

            errors = "\n".join(validate_repository(skills))
            self.assertIn("metadata.version must be a valid SemVer string", errors)
            self.assertIn(
                "compatibility check does not match scripts/compatibility_check.md",
                errors,
            )
            self.assertIn("missing local reference: scripts/missing.py", errors)
            self.assertIn("missing local reference: references/also-missing.md", errors)
            self.assertIn("invalid reference: http://[", errors)
            self.assertIn("invalid reference: file:///etc/passwd", errors)
            self.assertIn("invalid reference: references/%00.md", errors)
            self.assertIn("invalid reference: //example.com/path", errors)
            self.assertGreaterEqual(
                errors.count("update command must be the literal"), 2
            )
            self.assertIn("duplicate skill name 'valid-skill'", errors)
            self.assertIn("Invalid YAML", errors)

    def test_compatibility_manifest_must_match_published_skills(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            skills = repository / "skills"
            skill = skills / "example-skill"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                """---
name: example-skill
description: An example skill.
metadata:
  version: "2.1.0"
---
"""
            )
            manifest = repository / "public_ai_skills.yml"

            manifest.write_text(
                """shared:
  skills:
    example-skill:
      minimum_skill_version: "2.0.0"
      latest_skill_version: "2.0.0"
"""
            )
            self.assertIn(
                "example-skill: latest_skill_version 2.0.0 does not match metadata.version 2.1.0",
                validate_repository(skills),
            )

            manifest.write_text(
                """shared:
  skills:
    retired-skill:
      retired_on: "2026-01-03"
"""
            )
            self.assertIn(
                "example-skill: missing from public_ai_skills.yml",
                validate_repository(skills),
            )

            manifest.write_text(
                """shared:
  skills:
    example-skill:
      minimum_skill_version: "2.2.0"
      latest_skill_version: "2.1.0"
    missing-skill:
      minimum_skill_version: "1.0.0"
      latest_skill_version: "1.0.0"
    retired-skill:
      retired_on: "2026-01-03"
"""
            )
            errors = validate_repository(skills)
            self.assertIn(
                "example-skill: minimum_skill_version 2.2.0 is above latest_skill_version 2.1.0",
                errors,
            )
            self.assertIn(
                "missing-skill: active manifest entry has no skill directory", errors
            )
            self.assertNotIn(
                "retired-skill: active manifest entry has no skill directory", errors
            )


if __name__ == "__main__":
    unittest.main()
