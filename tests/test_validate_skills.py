import tempfile
import unittest
from pathlib import Path

from scripts.validate_skills import validate_repository


class ValidateSkillsTest(unittest.TestCase):
    def test_repository_policy_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            skills = Path(directory)
            self.assertIn(
                "Missing skills directory", validate_repository(skills / "missing")[0]
            )
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
Run `npx skills update valid-skill` when an update is required.
"""
            )
            self.assertEqual(validate_repository(skills), [])

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


if __name__ == "__main__":
    unittest.main()
