import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from runners.codex import parse_events


def test_parse_codex_events():
    fixture = Path(__file__).parent / "fixtures" / "codex_events.jsonl"

    result = parse_events(fixture.read_text().splitlines())

    assert result["toolCalls"] == [
        {
            "name": "command_execution",
            "input": {
                "command": "/bin/zsh -lc \"sed -n '1,20p' /invented/SKILL.md\""
            },
            "output": "---\nname: invented-skill\n",
            "isError": False,
        },
        {
            "name": "command_execution",
            "input": {"command": "/bin/zsh -lc \"invented-command\""},
            "output": "Invented command failure\n",
            "isError": True,
        },
        {
            "name": "whoami",
            "input": {},
            "output": "[{'type': 'text', 'text': '{\"person\":{\"name\":\"Invented Person\"}}'}]",
            "isError": False,
        },
        {
            "name": "list_invented_records",
            "input": {"limit": 1},
            "output": None,
            "isError": True,
        },
    ]
    assert result["usage"]["inputTokens"] == 1000
    assert result["usage"]["costUsd"] is None
    assert result["answer"] == "Connected and verified."


def test_codex_cost_is_unavailable_without_a_completed_turn():
    assert parse_events([])["usage"]["costUsd"] is None
