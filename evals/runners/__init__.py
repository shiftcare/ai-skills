import json
import subprocess
from pathlib import Path

from .codex import run as run_codex


CLAUDE_RUNNER = Path(__file__).with_name("claude.mjs")
DISPATCHERS = {"call_read_tool", "call_write_tool"}


def undispatch(call):
    """Record a call made through a progressive-discovery dispatcher under the
    tool it ran, so expected tools and per-tool metrics score the real call."""
    arguments = call.get("input") or {}
    if call["name"] not in DISPATCHERS or not isinstance(arguments.get("name"), str):
        return call
    return {**call, "name": arguments["name"], "input": arguments.get("arguments") or {}}


def run_agent(prompt, model, cwd, skill, mcp):
    result = _run(prompt, model, cwd, skill, mcp)
    result["toolCalls"] = [undispatch(call) for call in result["toolCalls"]]
    return result


def _run(prompt, model, cwd, skill, mcp):
    if model.startswith("gpt-"):
        return run_codex(prompt, model, cwd, mcp)

    completed = subprocess.run(
        ["node", str(CLAUDE_RUNNER)],
        input=json.dumps(
            {"prompt": prompt, "model": model, "cwd": cwd, "skill": skill, "mcp": mcp}
        ),
        capture_output=True,
        text=True,
        timeout=600,
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip())
    return json.loads(completed.stdout)
