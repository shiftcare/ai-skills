import os
from pathlib import Path
import subprocess
import sys


EVALS_DIR = Path(__file__).parents[1]


def test_mcp_token_is_redacted_from_pytest_tracebacks(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPEVAL", "1")
    sentinel = "invented-secret-token-for-redaction-test"
    test_file = tmp_path / "test_failure.py"
    test_file.write_text(
        "import os\n\n"
        "import conftest\n\n"
        "def test_failure():\n"
        "    print(f\"DEEPEVAL_STATE={os.environ.get('DEEPEVAL', 'missing')}\")\n"
        "    mcp = conftest.mcp.__wrapped__()\n"
        "    assert False\n"
    )
    env = {
        **os.environ,
        "MCP_URL": "https://mcp.example.invalid/mcp",
        "MCP_TOKEN": sentinel,
    }
    env.pop("DEEPEVAL", None)

    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "--showlocals", str(test_file)],
        cwd=EVALS_DIR,
        env=env,
        capture_output=True,
        text=True,
    )

    output = completed.stdout + completed.stderr
    assert completed.returncode == 1
    assert "DEEPEVAL_STATE=missing" in output
    assert sentinel not in output
    assert "<redacted>" in output
