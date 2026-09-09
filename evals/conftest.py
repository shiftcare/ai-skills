import json
import os
import subprocess
from pathlib import Path

import pytest


EVALS_DIR = Path(__file__).parent
DEFAULT_MODELS = "sonnet,haiku,gpt-5.6-terra,gpt-5.6-luna"


class McpConfig(dict):
    def __repr__(self):
        return repr({**self, "token": "<redacted>"})

    __str__ = __repr__


def env_value(name):
    value = os.environ.get(name)
    if value:
        return value
    try:
        lines = (EVALS_DIR / ".env").read_text().splitlines()
    except FileNotFoundError:
        return None
    for line in lines:
        key, separator, value = line.partition("=")
        if not separator or key.strip() != name:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        return value or None
    return None


def pytest_generate_tests(metafunc):
    if "model" in metafunc.fixturenames:
        models = [model.strip() for model in os.getenv("EVAL_MODELS", DEFAULT_MODELS).split(",")]
        metafunc.parametrize("model", [model for model in models if model])


@pytest.fixture(scope="session")
def workspaces():
    completed = subprocess.run(
        ["node", "workspace.mjs"],
        cwd=EVALS_DIR,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode:
        pytest.exit(completed.stderr.strip() or "Failed to create evaluation workspaces")
    return json.loads(completed.stdout)


@pytest.fixture(scope="session")
def mcp():
    url = env_value("MCP_URL")
    if not url:
        pytest.exit("MCP_URL is required in the environment or evals/.env")

    token = env_value("MCP_TOKEN")
    if not token:
        completed = subprocess.run(
            ["node", "auth.mjs", "token"],
            cwd=EVALS_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if completed.returncode:
            pytest.exit(
                completed.stderr.strip()
                or "No saved login. Run: cd evals && node auth.mjs login"
            )
        token = completed.stdout.strip()
    if not token:
        pytest.exit("No MCP token available. Run: cd evals && node auth.mjs login")
    return McpConfig(url=url, token=token)
