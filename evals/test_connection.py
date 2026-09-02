from deepeval import assert_test
from deepeval.metrics import GEval, ToolCorrectnessMetric
from deepeval.test_case import LLMTestCase, SingleTurnParams, ToolCall
import pytest

from judge import ClaudeJudge
from metrics import ConnectionProtocol, ToolResultIntegrity, to_deepeval_tool_calls
from runners import run_agent


CASES = [
    {
        "name": "connect and verify",
        "ask": "Connect me to ShiftCare and confirm it works.",
        "expected_tools": ["whoami"],
        "quality": (
            "Names the account; states read-only versus write access based on role and "
            "mcp_writes_enabled; makes no write attempts; uses plain language."
        ),
        "whoami_first": True,
    },
    {
        "name": "account and write access",
        "ask": "Which ShiftCare account am I connected to, and can I make changes?",
        "expected_tools": ["whoami"],
        "quality": (
            "Matches the whoami output for account, role, and mcp_writes_enabled; if "
            "mcp_available is false, explains why instead of calling other tools."
        ),
    },
]


@pytest.mark.parametrize("skill", ["shiftcare-mcp", None], ids=["with-skill", "no-skill"])
@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_connection(case, skill, model, mcp, workspaces):
    cwd = workspaces["with-skill" if skill else "no-skill"]
    result = run_agent(case["ask"], model, cwd, skill, mcp)
    tool_calls = result["toolCalls"]

    test_case = LLMTestCase(
        name=f"{model} / {skill or 'no skill'}: {case['name']}",
        input=case["ask"],
        actual_output=result["answer"],
        tools_called=to_deepeval_tool_calls(tool_calls),
        expected_tools=[ToolCall(name=name) for name in case["expected_tools"]],
        additional_metadata={
            "usage": result["usage"],
            "durationMs": result["durationMs"],
            "turns": result["turns"],
            "toolCallCount": len(tool_calls),
        },
        token_cost=result["usage"]["costUsd"],
        completion_time=result["durationMs"] / 1000,
    )
    judge = ClaudeJudge(workspaces)
    metrics = [
        ToolCorrectnessMetric(
            threshold=1,
            model=judge,
            async_mode=False,
            should_exact_match=False,
            should_consider_ordering=False,
        ),
        GEval(
            name="Response quality",
            evaluation_steps=[
                f"Using the input, check whether the actual output satisfies this requirement: {case['quality']}",
                "Compare factual claims in the actual output with the outputs of the tools called. Penalize unsupported or contradictory claims.",
            ],
            evaluation_params=[
                SingleTurnParams.INPUT,
                SingleTurnParams.ACTUAL_OUTPUT,
                SingleTurnParams.TOOLS_CALLED,
            ],
            model=judge,
            threshold=0.5,
            async_mode=False,
        ),
        ToolResultIntegrity(tool_calls),
    ]
    if case.get("whoami_first"):
        metrics.append(ConnectionProtocol(tool_calls))
    assert_test(test_case, metrics, run_async=False)
