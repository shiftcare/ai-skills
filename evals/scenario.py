from datetime import date, timedelta

from deepeval import assert_test
from deepeval.metrics import GEval, ToolCorrectnessMetric
from deepeval.test_case import LLMTestCase, SingleTurnParams, ToolCall

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


def evaluate(case, skill, model, mcp, workspaces, suite, scenario_file):
    result = run_agent(
        case["ask"],
        model,
        workspaces["skills"][skill] if skill else workspaces["no-skill"],
        skill=skill,
        mcp=mcp,
    )
    tool_calls = result["toolCalls"]

    test_case = LLMTestCase(
        name=f"{model} / {skill or 'no skill'}: {case['name']}",
        input=case["ask"],
        actual_output=result["answer"],
        tools_called=to_deepeval_tool_calls(tool_calls),
        expected_tools=[ToolCall(name=name) for name in case["expected_tools"]],
        additional_metadata={
            "suite": suite,
            "case": case["name"],
            "model": model,
            "skillHash": skill_hash(skill),
            "scenarioHash": cases_hash(scenario_file),
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
    # activates=None opts a case out of activation scoring: a boundary case such
    # as "move this shift", asked with cancel-shift installed, is right whether
    # the skill loads and refuses or never loads at all.
    activates = case.get("activates", True)
    if skill and activates is not None:
        metrics.append(SkillActivation(tool_calls, expected=activates, skill=skill))
    if case.get("shift_date"):
        offset = {"yesterday": -1, "today": 0, "tomorrow": 1}[case["shift_date"]]
        metrics.append(
            ShiftDate(tool_calls, (date.today() + timedelta(days=offset)).isoformat())
        )
    assert_test(test_case, metrics, run_async=True)
