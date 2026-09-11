import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize(("workers", "expected"), [(None, "4"), ("2", "2")])
def test_run_script_uses_bounded_parallel_workers(tmp_path, workers, expected):
    evals = tmp_path / "evals"
    evals.mkdir()
    shutil.copy(Path(__file__).parents[1] / "run.sh", evals / "run.sh")
    for name in ("test_alpha.py", "test_beta.py", "test_gamma.py"):
        (evals / name).write_text("")
    fake_uv = tmp_path / "uv"
    fake_uv.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    fake_uv.chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"}
    if workers:
        env["EVAL_WORKERS"] = workers
    else:
        env.pop("EVAL_WORKERS", None)

    completed = subprocess.run(
        [evals / "run.sh", "-k", "connection"],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )

    # run.sh also archives and reports after the run, so scope this to the
    # pytest invocation rather than asserting on the whole transcript.
    assert completed.stdout.splitlines()[:11] == [
        "run", "deepeval", "test", "run", "test_alpha.py", "test_beta.py",
        "test_gamma.py", "-n", expected, "-k", "connection",
    ]


def _fake_uv(tmp_path, pytest_exit=0, writes_results=True):
    """A `uv` stub that logs its arguments and can simulate failing tests.

    A real `deepeval test run` rewrites .latest_run_full.json, and run.sh only
    archives results newer than the run start, so the stub touches that file
    too. `writes_results=False` simulates an interrupted run that leaves the
    previous results behind.
    """
    log = tmp_path / "calls.log"
    fake_uv = tmp_path / "uv"
    touch = 'touch .deepeval/.latest_run_full.json\n' if writes_results else ""
    fake_uv.write_text(
        "#!/bin/sh\n"
        f'printf "%s\\n" "$*" >> "{log}"\n'
        f'case "$*" in *"deepeval test run"*) {touch}exit {pytest_exit};; esac\n'
        "exit 0\n"
    )
    fake_uv.chmod(0o755)
    return fake_uv, log


def _run(tmp_path, expect_code=0, script=None):
    # run.sh cd's to its own directory, so an isolated run means invoking the
    # copied script, not passing a different cwd to the real one.
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"}
    env.pop("EVAL_WORKERS", None)
    completed = subprocess.run(
        [script or Path(__file__).parents[1] / "run.sh"],
        capture_output=True, text=True, env=env,
    )
    assert completed.returncode == expect_code, completed.stderr
    return completed


@pytest.fixture
def eval_copy(tmp_path):
    """A throwaway copy of the harness.

    run.sh cd's to its own directory and writes into .deepeval/ and runs/, so
    tests that let it archive must not run against the real 38MB result pool.
    """
    root = tmp_path / "evals"
    root.mkdir()
    source = Path(__file__).parents[1]
    shutil.copy(source / "run.sh", root / "run.sh")
    (root / "report.py").write_text("")
    (root / ".deepeval").mkdir()
    (root / ".deepeval" / ".latest_run_full.json").write_text("{}")
    os.utime(root / ".deepeval" / ".latest_run_full.json", (1, 1))
    # run.sh archives to ../runs, a sibling of the harness directory.
    return root


def test_run_script_generates_report_after_a_passing_run(tmp_path, eval_copy):
    _, log = _fake_uv(tmp_path)

    _run(tmp_path, script=eval_copy / "run.sh")

    assert "report.py" in log.read_text()
    assert len(list((eval_copy.parent / "runs").glob("*.json"))) == 1


def test_run_script_generates_report_even_when_tests_fail(tmp_path, eval_copy):
    """A failing matrix is exactly the run that needs reading, so the report
    and its archive are still produced."""
    _, log = _fake_uv(tmp_path, pytest_exit=1)

    _run(tmp_path, expect_code=1, script=eval_copy / "run.sh")

    assert "report.py" in log.read_text()
    assert len(list((eval_copy.parent / "runs").glob("*.json"))) == 1


def test_run_script_does_not_rearchive_stale_results(tmp_path, eval_copy):
    """An interrupted run leaves the previous results in place; archiving them
    again would double-count that matrix into the pooled report."""
    _fake_uv(tmp_path, writes_results=False)

    completed = _run(tmp_path, script=eval_copy / "run.sh")

    assert "no new results written" in completed.stderr
    assert list((eval_copy.parent / "runs").glob("*.json")) == []
