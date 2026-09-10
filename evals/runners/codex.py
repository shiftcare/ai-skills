import json
import os
import subprocess
import sys
import time
from pathlib import Path


# The same allowlist the Claude runner enforces. Codex's `-s read-only` sandboxes
# model-generated shell commands, not MCP tool calls, so without this the Codex
# arm can call any tool the server exposes, writes included.
READ_TOOLS = json.loads((Path(__file__).parents[1] / "read_tools.json").read_text())


def parse_events(lines):
    answer = ""
    tool_calls = []
    usage = {"inputTokens": 0, "outputTokens": 0, "costUsd": None}
    turns = 0

    for line in lines:
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("type") == "item.completed":
            item = event.get("item") or {}
            if item.get("type") == "agent_message":
                answer = item.get("text", "")
            elif item.get("type") == "command_execution":
                tool_calls.append(
                    {
                        "name": "command_execution",
                        "input": {"command": item.get("command")},
                        "output": item.get("aggregated_output"),
                        "isError": item.get("exit_code") not in (None, 0, "0"),
                    }
                )
            elif item.get("type") == "mcp_tool_call":
                result = item.get("result")
                tool_calls.append(
                    {
                        "name": item["tool"],
                        "input": item.get("arguments") or {},
                        "output": result.get("content") if isinstance(result, dict) else None,
                        "isError": item.get("error") is not None
                        or item.get("status") == "failed",
                    }
                )
        elif event.get("type") == "turn.completed":
            raw_usage = event.get("usage") or {}
            usage = {
                "inputTokens": raw_usage.get("input_tokens", 0),
                "outputTokens": raw_usage.get("output_tokens", 0),
                "costUsd": None,
            }
            turns += 1

    return {
        "answer": answer,
        "toolCalls": tool_calls,
        "usage": usage,
        "durationMs": 0,
        "turns": turns,
    }


def run(prompt, model, cwd, mcp):
    if not all(isinstance(value, str) for value in (prompt, model, cwd)):
        raise ValueError("prompt, model, and cwd must be strings")
    if mcp is not None and not all(isinstance(mcp.get(key), str) for key in ("url", "token")):
        raise ValueError("mcp.url and mcp.token must be strings")

    command = [
        "codex",
        "exec",
        "--json",
        "--ephemeral",
        "--ignore-user-config",
        "--skip-git-repo-check",
        "-s",
        "read-only",
        "-m",
        model,
        "-C",
        cwd,
        "--color",
        "never",
    ]
    codex_home = os.path.join(os.path.dirname(cwd), "home")
    if not os.path.isdir(codex_home):
        raise ValueError(
            f"Codex isolation home does not exist: {codex_home}. "
            "Run node evals/workspace.mjs first."
        )

    env = os.environ.copy()
    # Codex otherwise discovers the user's personal skills and plugins from HOME.
    env["HOME"] = codex_home
    if mcp is not None:
        command.extend(
            [
                "-c",
                f"mcp_servers.shiftcare.url={json.dumps(mcp['url'])}",
                "-c",
                'mcp_servers.shiftcare.bearer_token_env_var="MCP_TOKEN"',
                "-c",
                'mcp_servers.shiftcare.http_headers={ Accept = "application/json, text/event-stream" }',
                "-c",
                f"mcp_servers.shiftcare.enabled_tools={json.dumps(READ_TOOLS)}",
            ]
        )
        env["MCP_TOKEN"] = mcp["token"]
    command.extend(["-c", 'model_reasoning_effort="medium"', prompt])

    started = time.monotonic()
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        env=env,
        stdin=subprocess.DEVNULL,
    )
    duration_ms = round((time.monotonic() - started) * 1000)
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or f"codex exited with status {completed.returncode}")
    result = parse_events(completed.stdout.splitlines())
    result["durationMs"] = duration_ms
    return result


def main():
    request = json.load(sys.stdin)
    json.dump(
        run(request["prompt"], request["model"], request["cwd"], request.get("mcp")),
        sys.stdout,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None
