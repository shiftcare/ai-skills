import pytest
from deepeval.test_case import LLMTestCase, ToolCall

from judge import ClaudeJudge
import metrics
from metrics import ConnectionProtocol, ToolResultIntegrity


TEST_CASE = LLMTestCase(input="Invented input", actual_output="Invented output")


def measured(calls):
    metric = ToolResultIntegrity(calls)
    return metric, metric.measure(TEST_CASE)


def test_tool_result_integrity_passes_complete_results():
    metric, score = measured(
        [{"name": "whoami", "output": "Invented output", "isError": False}]
    )

    assert score == 1
    assert metric.is_successful()


def test_tool_result_integrity_fails_errors():
    metric, score = measured(
        [{"name": "whoami", "output": "Invented failure", "isError": True}]
    )

    assert score == 0
    assert "whoami" in metric.reason


def test_tool_result_integrity_fails_missing_output():
    metric, score = measured(
        [{"name": "list_teams", "output": None, "isError": False}]
    )

    assert score == 0
    assert "list_teams" in metric.reason


@pytest.mark.parametrize(
    "output",
    [
        "Result exceeds maximum allowed tokens",
        "Output has been saved to an invented file",
    ],
)
def test_tool_result_integrity_fails_truncated_output(output):
    metric, score = measured(
        [{"name": "list_clients", "output": output, "isError": False}]
    )

    assert score == 0
    assert "list_clients" in metric.reason



@pytest.mark.parametrize(
    ("names", "expected"),
    [
        (["Skill", "whoami", "list_teams"], 1),
        (["command_execution", "whoami", "list_clients"], 1),
        (["whoami"], 0),
        (["whoami", "whoami"], 0),
        (["whoami", "write_tool"], 0),
        (["whoami", "list_invented_unsupported_records"], 0),
        (["whoami", "list_shifts"], 1),
        (["whoami", "list_invoices"], 1),
        (["list_teams", "whoami"], 0),
        ([], 0),
    ],
)
def test_connection_protocol(names, expected):
    metric = ConnectionProtocol([{"name": name} for name in names])

    assert metric.measure(TEST_CASE) == expected


def test_agentic_metrics_include_completion_efficiency_and_arguments(monkeypatch):
    monkeypatch.delenv("EVAL_JUDGE_MODEL", raising=False)
    judge = ClaudeJudge({"no-skill": "/tmp/invented-workspace"})

    names = [metric.__name__ for metric in metrics.agentic_metrics(judge, "Invented task")]

    assert names == ["Task Completion", "Step Efficiency", "Argument Correctness"]


def test_agentic_metrics_are_async(monkeypatch):
    monkeypatch.delenv("EVAL_JUDGE_MODEL", raising=False)
    judge = ClaudeJudge({"no-skill": "/tmp/invented-workspace"})

    assert all(metric.async_mode for metric in metrics.agentic_metrics(judge, "Invented task"))


def test_argument_correctness_ignores_infrastructure_and_argumentless_tools():
    test_case = LLMTestCase(
        input="Invented input",
        actual_output="Invented output",
        tools_called=[
            ToolCall(name="command_execution", input_parameters={"command": "invented"}),
            ToolCall(name="whoami", input_parameters={}),
            ToolCall(name="list_teams", input_parameters={"page": 2}),
        ],
    )

    filtered = metrics._argument_correctness_case(test_case)

    assert [call.name for call in filtered.tools_called] == ["list_teams"]


def test_agent_trace_preserves_tool_order_and_arguments():
    trace = metrics.agent_trace(
        TEST_CASE,
        [
            {
                "name": "whoami",
                "input": {},
                "output": "Invented account",
                "isError": False,
            },
            {
                "name": "list_teams",
                "input": {"page": 2},
                "output": "Invented team",
                "isError": False,
            },
        ],
    )

    assert trace == {
        "name": "agent",
        "type": "agent",
        "input": "Invented input",
        "output": "Invented output",
        "children": [
            {
                "name": "whoami",
                "type": "tool",
                "input": {"inputParameters": {}},
                "output": "Invented account",
                "error": None,
                "children": [],
            },
            {
                "name": "list_teams",
                "type": "tool",
                "input": {"inputParameters": {"page": 2}},
                "output": "Invented team",
                "error": None,
                "children": [],
            },
        ],
    }
