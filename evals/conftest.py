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


@pytest.fixture
def mcp():
    """Resolved per test on purpose. MCP access tokens expire after 300
    seconds, so a session-scoped fixture hands every test after the first few
    minutes an expired token and the agents silently lose their ShiftCare
    tools. `auth.mjs token` reuses a token with more than 30 seconds left and
    refreshes it otherwise, so per-test resolution costs one subprocess call."""
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


INFRASTRUCTURE_ERRORS_BEFORE_EXIT = 3
consecutive_infrastructure_errors = 0


def infrastructure_error(excinfo):
    """A failed assertion is a result. Anything else a scenario raises (the agent
    runner exiting non-zero, a subprocess timeout, the judge's SDK rejecting a
    call) means the evaluation never happened."""
    return (
        excinfo is not None
        and excinfo.errisinstance(Exception)
        and not excinfo.errisinstance(AssertionError)
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Flag scenario errors on the worker, where the exception is still in hand.
    Only scenarios (anything taking the `model` fixture) count: a broken unit
    test under tests/ is not an outage."""
    report = (yield).get_result()
    if call.when == "call" and "model" in item.fixturenames:
        report.infrastructure_error = infrastructure_error(call.excinfo)


def pytest_runtest_logreport(report):
    """End the session after a run of infrastructure errors.

    A quota outage fails every remaining scenario, each spawning an agent and up
    to a dozen judge subprocesses that fail in turn. `--maxfail` is the wrong
    tool because legitimate metric failures are common, so only consecutive
    infrastructure errors count and any real result resets the run. Under xdist
    this hook runs in the controller; `pytest.exit` from the worker-side hook
    trips an xdist internal error instead of a clean stop."""
    global consecutive_infrastructure_errors
    if report.when != "call":
        return
    if getattr(report, "infrastructure_error", False):
        consecutive_infrastructure_errors += 1
    else:
        consecutive_infrastructure_errors = 0
    if consecutive_infrastructure_errors >= INFRASTRUCTURE_ERRORS_BEFORE_EXIT:
        pytest.exit(
            f"{consecutive_infrastructure_errors} consecutive infrastructure errors; "
            f"last: {report.longrepr.reprcrash.message}",
            returncode=3,
        )
