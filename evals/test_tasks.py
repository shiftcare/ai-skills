from datetime import date, timedelta
import json

from deepeval import assert_test
from deepeval.metrics import GEval, ToolCorrectnessMetric
from deepeval.test_case import LLMTestCase, SingleTurnParams, ToolCall
import pytest

from judge import ClaudeJudge
from metrics import ToolResultIntegrity, agent_trace, agentic_metrics, to_deepeval_tool_calls
from runners import run_agent


CASES = [
    {
        "name": "client lookup picks list_clients",
        "ask": "What active clients do we have?",
        "expected_tool": "list_clients",
        "quality": (
            "Lists one or more real clients from the account; does not fabricate or "
            "claim it has no access."
        ),
    },
    {
        "name": "schedule question picks list_shifts with tomorrow's date",
        "ask": "What shifts are scheduled for tomorrow?",
        "expected_tool": "list_shifts",
        "quality": (
            "Reports tomorrow's shifts (or clearly states there are none); does not "
            "invent shifts."
        ),
    },
    {
        "name": "invoice question picks list_invoices",
        "ask": "Do we have any unpaid invoices?",
        "expected_tool": "list_invoices",
        "quality": (
            "Answers based on actual invoice data (or clearly states none found); does "
            "not fabricate amounts."
        ),
    },
]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_task(case, model, mcp, workspaces):
    result = run_agent(
        case["ask"],
        model,
        workspaces["no-skill"],
        skill=None,
        mcp=mcp,
    )
    tool_calls = result["toolCalls"]

    if case["expected_tool"] == "list_shifts":
        shift_call = next(
            (call for call in tool_calls if call["name"] == "list_shifts"),
            None,
        )
        assert shift_call is not None
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        assert tomorrow in json.dumps(shift_call["input"])

    test_case = LLMTestCase(
        name=f"{model}: {case['name']}",
        input=case["ask"],
        actual_output=result["answer"],
        tools_called=to_deepeval_tool_calls(tool_calls),
        expected_tools=[ToolCall(name=case["expected_tool"])],
        additional_metadata={
            "suite": "Read-only tasks",
            "case": case["name"],
            "model": model,
            "skillVariant": "No skill",
            "usage": result["usage"],
            "durationMs": result["durationMs"],
            "turns": result["turns"],
            "toolCallCount": len(tool_calls),
        },
        token_cost=result["usage"]["costUsd"],
        completion_time=result["durationMs"] / 1000,
    )
    test_case._trace_dict = agent_trace(test_case, tool_calls)
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
        *agentic_metrics(judge, case["ask"]),
    ]
    assert_test(test_case, metrics, run_async=False)
