# ShiftCare AI Skills

Skills that teach AI coding agents how to work with [ShiftCare](https://www.shiftcare.com) through the ShiftCare MCP server.

## Install

Install every skill in this collection:

```
npx skills add shiftcare/ai-skills
```

Install one skill by name:

```
npx skills add shiftcare/ai-skills -s shiftcare-mcp
```

Update installed skills later:

```
npx skills update
```

## Validate

Run every static skill check locally with:

```
uv run --with skills-ref==0.1.1 scripts/validate_skills.py
```

## Skills

| Skill | What it does |
| --- | --- |
| [`shiftcare-mcp`](skills/shiftcare-mcp/SKILL.md) | Connect an agent to the ShiftCare MCP server and verify the connection. |
| [`onboarding-check`](skills/onboarding-check/SKILL.md) | Read-only setup scorecard for a new account, with the next help article for each gap. |

## Requirements

- A ShiftCare account with MCP enabled by an Admin under **Account → AI Settings**.
- An AI agent that supports MCP and skills. We test Claude Code and Codex. Other agents may work but are untested.

## Telemetry

The installer is Vercel's open-source `skills` CLI, which sends anonymous install events. Set `DISABLE_TELEMETRY=1` to turn that off.

## License

Apache-2.0. See [LICENSE](LICENSE).
