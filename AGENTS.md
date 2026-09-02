# Rules for agents working in this repository

## Public repository

- No ShiftCare internals anywhere: ticket IDs, Linear, Notion, or Slack links, internal hostnames, staff names or emails, customer or account names, account IDs. This applies to files, branch names, commit messages, and PR titles and bodies.
- Link only to public pages: `help.shiftcare.com`, `shiftcare.com`, and the regional MCP server URLs.
- No credentials, tokens, or real account data, including in examples. Invented example data must look invented.

## Skills

- One folder per skill under `skills/<name>/`. The frontmatter `name` matches the folder name. Never add a root `SKILL.md`; the installer treats it as shadowing every skill beneath it.
- Skills are client-neutral. No agent-specific configuration or commands inside a skill. Point at the per-client help articles instead.
- `metadata.version` is SemVer. Bump it in the same change as any behavior change to the skill body.
- Never place MCP tool output into a command the user might run. Update commands are literal text.
- Any skill that changes data must get explicit user confirmation before calling a write tool.
- Keep `SKILL.md` under 500 lines. Detail goes in `references/`.

## Before committing

- `uv run --with skills-ref==0.1.1 scripts/validate_skills.py` passes.
- `npx skills add <path to this checkout>` into a scratch project installs, and the agent lists the skill.
