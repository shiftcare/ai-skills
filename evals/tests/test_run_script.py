import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize(("workers", "expected"), [(None, "4"), ("2", "2")])
def test_run_script_uses_bounded_parallel_workers(tmp_path, workers, expected):
    fake_uv = tmp_path / "uv"
    fake_uv.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    fake_uv.chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"}
    if workers:
        env["EVAL_WORKERS"] = workers
    else:
        env.pop("EVAL_WORKERS", None)

    completed = subprocess.run(
        [Path(__file__).parents[1] / "run.sh", "-k", "connection"],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )

    # run.sh also archives and reports after the run, so scope this to the
    # pytest invocation rather than asserting on the whole transcript.
    assert completed.stdout.splitlines()[:10] == [
        "run", "deepeval", "test", "run", "test_connection.py", "test_tasks.py",
        "-n", expected, "-k", "connection",
    ]


def _fake_uv(tmp_path, pytest_exit=0):
    """A `uv` stub that logs its arguments and can simulate failing tests."""
    log = tmp_path / "calls.log"
    fake_uv = tmp_path / "uv"
    fake_uv.write_text(
        "#!/bin/sh\n"
        f'printf "%s\\n" "$*" >> "{log}"\n'
        f'case "$*" in *"deepeval test run"*) exit {pytest_exit};; esac\n'
        "exit 0\n"
    )
    fake_uv.chmod(0o755)
    return fake_uv, log


def _run(tmp_path, expect_code=0):
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"}
    env.pop("EVAL_WORKERS", None)
    completed = subprocess.run(
        [Path(__file__).parents[1] / "run.sh"],
        capture_output=True, text=True, env=env,
    )
    assert completed.returncode == expect_code, completed.stderr
    return completed


def test_run_script_generates_report_after_a_passing_run(tmp_path):
    _, log = _fake_uv(tmp_path)

    _run(tmp_path)

    assert "report.py" in log.read_text()


def test_run_script_generates_report_even_when_tests_fail(tmp_path):
    """A failing matrix is exactly the run that needs reading, so the report
    must still be generated; only the script's exit status reflects failure."""
    _, log = _fake_uv(tmp_path, pytest_exit=1)

    _run(tmp_path, expect_code=1)

    assert "report.py" in log.read_text()
