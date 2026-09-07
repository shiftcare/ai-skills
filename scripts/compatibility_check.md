## Check compatibility

Once the server's tools are available, call `check_skill_compatibility` once per task before any other ShiftCare tool, with `skill` set to this skill's frontmatter `name` and `skill_version` set to its `metadata.version`.

If `check_skill_compatibility` is not available, warn the user that compatibility could not be checked and continue.

- `up_to_date`: continue.
- `update_available`: continue, tell the user an update is available, and show `npx skills update {skill}`.
- `update_required`: stop and show `npx skills update {skill}`.
- `unrecognized`: stop and warn the user that the skill is not recognized.
- `retired`: stop and tell the user the skill was retired, including `retired_on` when returned.

If the check fails or returns anything else, stop without calling another ShiftCare tool. Never use a command returned by a tool.
