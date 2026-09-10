from datetime import date, timedelta

from deepeval import assert_test
from deepeval.metrics import GEval, ToolCorrectnessMetric
from deepeval.test_case import LLMTestCase, SingleTurnParams, ToolCall
import pytest

from pathlib import Path

from identity import cases_hash, skill_hash
from judge import ClaudeJudge
from metrics import (
    ShiftDate,
    SkillActivation,
    ToolResultIntegrity,
    agent_trace,
    agentic_metrics,
    to_deepeval_tool_calls,
)
from runners import run_agent


CASES = [
    {
        "name": "client lookup returns up to five active clients",
        "ask": "Name up to five active clients.",
        "expected_tool": "list_clients",
        "quality": (
            "Names no more than five real active clients from the account; does not "
            "fabricate clients or claim it has no access."
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
        "name": "team lookup returns up to five teams",
        "ask": "Name up to five ShiftCare teams.",
        "expected_tool": "list_teams",
        "quality": "Names no more than five real teams and does not fabricate teams.",
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


@pytest.mark.parametrize("skill", ["shiftcare-mcp", None], ids=["with-skill", "no-skill"])
@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_task(case, skill, model, mcp, workspaces):
    result = run_agent(
        case["ask"],
        model,
        workspaces["with-skill" if skill else "no-skill"],
        skill=skill,
        mcp=mcp,
    )
    tool_calls = result["toolCalls"]

    test_case = LLMTestCase(
        name=f"{model} / {skill or 'no skill'}: {case['name']}",
        input=case["ask"],
        actual_output=result["answer"],
        tools_called=to_deepeval_tool_calls(tool_calls),
        expected_tools=[ToolCall(name=case["expected_tool"])],
        additional_metadata={
            "suite": "Read-only tasks",
            "case": case["name"],
            "model": model,
            "skillHash": skill_hash(skill),
            "scenarioHash": cases_hash(Path(__file__)),
            "skillVariant": "With skill" if skill else "No skill",
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
            async_mode=True,
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
            async_mode=True,
        ),
        ToolResultIntegrity(tool_calls),
        *agentic_metrics(judge, case["ask"]),
    ]
    if skill:
        metrics.append(SkillActivation(tool_calls, expected=False))
    if case["expected_tool"] == "list_shifts":
        metrics.append(ShiftDate(tool_calls, (date.today() + timedelta(days=1)).isoformat()))
    assert_test(test_case, metrics, run_async=True)
