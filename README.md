# ShiftCare AI Skills

Skills that teach AI coding agents how to work with [ShiftCare](https://www.shiftcare.com) through the ShiftCare MCP server.

A skill is a folder with a `SKILL.md` file. Your agent reads it when a task matches, so it knows the right steps, tools, and safety checks instead of improvising.

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

Updates never run in the background. You choose when to update.

## Skills

| Skill | What it does |
| --- | --- |
| [`shiftcare-mcp`](skills/shiftcare-mcp/SKILL.md) | Connect an agent to the ShiftCare MCP server and verify the connection. |

## Requirements

- A ShiftCare account with MCP enabled by an Admin under **Account → AI Settings**.
- An AI agent that supports MCP and skills. We test Claude Code and Codex. Other agents may work but are untested.

## Telemetry

The installer is Vercel's open-source `skills` CLI, which sends anonymous install events. Set `DISABLE_TELEMETRY=1` to turn that off. ShiftCare adds no telemetry to the skills themselves and never sees your prompts or conversations.

## License

Apache-2.0. See [LICENSE](LICENSE).
