import json
import subprocess
from pathlib import Path

from .codex import run as run_codex


CLAUDE_RUNNER = Path(__file__).with_name("claude.mjs")


def run_agent(prompt, model, cwd, skill, mcp):
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
