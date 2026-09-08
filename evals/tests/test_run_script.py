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

    assert completed.stdout.splitlines() == [
        "run", "deepeval", "test", "run", "test_connection.py", "test_tasks.py",
        "-n", expected, "-k", "connection",
    ]
