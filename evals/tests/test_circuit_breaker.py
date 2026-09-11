import pytest

import conftest


class Report:
    when = "call"

    def __init__(self, infrastructure_error):
        self.infrastructure_error = infrastructure_error
        crash = type("Crash", (), {"message": "RuntimeError: usage limit reached"})()
        self.longrepr = type("Longrepr", (), {"reprcrash": crash})()


def test_only_non_assertion_exceptions_are_infrastructure():
    def excinfo(error):
        try:
            raise error
        except Exception:
            return pytest.ExceptionInfo.from_current()

    assert conftest.infrastructure_error(excinfo(RuntimeError("agent exited 1")))
    assert not conftest.infrastructure_error(excinfo(AssertionError("metric failed")))
    assert not conftest.infrastructure_error(None)


def test_session_ends_after_consecutive_infrastructure_errors(monkeypatch):
    """Two errors, a real result, then three errors: the result resets the run,
    so only the third error of the second run ends the session."""
    monkeypatch.setattr(conftest, "consecutive_infrastructure_errors", 0)
    for flag in (True, True, False, True, True):
        conftest.pytest_runtest_logreport(Report(flag))

    with pytest.raises(pytest.exit.Exception) as exit_info:
        conftest.pytest_runtest_logreport(Report(True))

    assert "3 consecutive infrastructure errors" in str(exit_info.value)
    assert "usage limit reached" in str(exit_info.value)
