import pytest
from deepeval.test_case import LLMTestCase

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
        (["list_teams", "whoami"], 0),
        ([], 0),
    ],
)
def test_connection_protocol(names, expected):
    metric = ConnectionProtocol([{"name": name} for name in names])

    assert metric.measure(TEST_CASE) == expected
