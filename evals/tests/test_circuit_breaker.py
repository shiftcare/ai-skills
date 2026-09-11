import json
import urllib.error
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

import conftest


class Report:
    def __init__(self, infrastructure_error, when="call"):
        self.when = when
        self.infrastructure_error = infrastructure_error
        crash = type("Crash", (), {"message": "RuntimeError: usage limit reached"})()
        self.longrepr = type("Longrepr", (), {"reprcrash": crash})()


def exception_info(error):
    try:
        raise error
    except Exception:
        return pytest.ExceptionInfo.from_current()


def make_report(fixturenames, when, error):
    report = SimpleNamespace(when=when)
    hook = conftest.pytest_runtest_makereport(
        SimpleNamespace(fixturenames=fixturenames),
        SimpleNamespace(when=when, excinfo=exception_info(error)),
    )
    next(hook)
    with pytest.raises(StopIteration):
        hook.send(SimpleNamespace(get_result=lambda: report))
    return report


def test_only_non_assertion_exceptions_are_infrastructure():
    assert conftest.infrastructure_error(exception_info(RuntimeError("agent exited 1")))
    assert not conftest.infrastructure_error(exception_info(AssertionError("metric failed")))
    assert not conftest.infrastructure_error(None)


@pytest.mark.parametrize(
    ("fixturenames", "expected"),
    [(["model"], True), ([], False)],
)
def test_setup_errors_are_only_infrastructure_for_scenarios(fixturenames, expected):
    report = make_report(fixturenames, "setup", RuntimeError("login failed"))

    assert getattr(report, "infrastructure_error", False) is expected


def test_session_ends_after_consecutive_infrastructure_errors(monkeypatch):
    """Two errors, a real result, then three errors: the result resets the run,
    while successful setup reports between calls do not."""
    monkeypatch.setattr(conftest, "consecutive_infrastructure_errors", 0)
    for flag in (True, True, False, True, True):
        conftest.pytest_runtest_logreport(Report(False, when="setup"))
        conftest.pytest_runtest_logreport(Report(flag))

    conftest.pytest_runtest_logreport(Report(False, when="setup"))
    with pytest.raises(pytest.exit.Exception) as exit_info:
        conftest.pytest_runtest_logreport(Report(True))

    assert "3 consecutive infrastructure errors" in str(exit_info.value)
    assert "usage limit reached" in str(exit_info.value)


def test_workers_leave_the_exit_to_the_controller(monkeypatch):
    monkeypatch.setattr(conftest, "consecutive_infrastructure_errors", 0)
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")
    for _ in range(4):
        conftest.pytest_runtest_logreport(Report(True))

    assert conftest.consecutive_infrastructure_errors == 0


def test_setup_infrastructure_errors_end_the_session(monkeypatch):
    monkeypatch.setattr(conftest, "consecutive_infrastructure_errors", 0)
    for _ in range(2):
        conftest.pytest_runtest_logreport(Report(True, when="setup"))

    with pytest.raises(pytest.exit.Exception) as exit_info:
        conftest.pytest_runtest_logreport(Report(True, when="setup"))

    assert "3 consecutive infrastructure errors" in str(exit_info.value)
    assert "usage limit reached" in str(exit_info.value)


def test_mcp_probe_accepts_2xx(monkeypatch):
    def urlopen(request, timeout):
        assert request.full_url == "https://mcp.example.test/mcp"
        assert request.method == "POST"
        assert request.get_header("Content-type") == "application/json"
        assert request.get_header("Accept") == "application/json, text/event-stream"
        assert request.get_header("Authorization") == "Bearer invented-token"
        assert request.get_header("User-agent") == "shiftcare-evals-preflight/0"
        assert json.loads(request.data) == {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "evals-preflight", "version": "0"},
            },
        }
        assert timeout == 30
        return nullcontext(SimpleNamespace(status=204))

    monkeypatch.setattr(conftest.urllib.request, "urlopen", urlopen)

    conftest.probe_mcp(
        conftest.McpConfig(
            url="https://mcp.example.test/mcp", token="invented-token"
        )
    )


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (
            urllib.error.HTTPError(
                "https://mcp.example.test/mcp", 401, "Unauthorized", {}, None
            ),
            "HTTP 401",
        ),
        (urllib.error.URLError("connection refused"), "connection refused"),
    ],
)
def test_mcp_probe_rejects_http_and_connection_errors(monkeypatch, error, message):
    def urlopen(request, timeout):
        raise error

    monkeypatch.setattr(conftest.urllib.request, "urlopen", urlopen)

    with pytest.raises(RuntimeError, match=message):
        conftest.probe_mcp(
            conftest.McpConfig(
                url="https://mcp.example.test/mcp", token="invented-token"
            )
        )
