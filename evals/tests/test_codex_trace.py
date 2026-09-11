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


def test_codex_restricts_mcp_tools_to_the_shared_allowlist(monkeypatch, tmp_path):
    """Codex's `-s read-only` sandboxes shell commands, not MCP calls, so without
    an explicit allowlist the Codex arm could call any tool the server exposes.
    Verified against the live server: the agent enumerates exactly these tools and
    reports anything else as unavailable."""
    import json as json_module
    import subprocess as subprocess_module
    from pathlib import Path as PathType

    from runners import codex

    home = tmp_path / "home"
    home.mkdir()
    workspace = tmp_path / "with-skill"
    workspace.mkdir()
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        return subprocess_module.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(codex.subprocess, "run", fake_run)
    codex.run("Invented prompt", "invented-model", str(workspace),
              {"url": "https://invented.example/mcp", "token": "invented-token"})

    allowlist = json_module.loads((PathType(codex.__file__).parents[1] / "read_tools.json").read_text())
    setting = next(
        argument for argument in captured["command"]
        if argument.startswith("mcp_servers.shiftcare.enabled_tools=")
    )

    assert json_module.loads(setting.split("=", 1)[1]) == allowlist
    assert "check_skill_compatibility" in allowlist


def test_codex_run_times_out_like_the_claude_runner(monkeypatch, tmp_path):
    """A Codex process stalled on a rate limit otherwise blocks its xdist worker
    for the rest of the run; the Claude runner already gives up after 600s."""
    import subprocess as subprocess_module

    from runners import codex

    (tmp_path / "home").mkdir()
    captured = {}

    def fake_run(command, **kwargs):
        captured.update(kwargs)
        return subprocess_module.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(codex.subprocess, "run", fake_run)
    codex.run("Invented prompt", "invented-model", str(tmp_path / "with-skill"), None)

    assert captured["timeout"] == 600
