from datetime import date, timedelta
from importlib import import_module

import pytest

from runners.codex import parse_events


def capture_scenario(monkeypatch, module_name, result, case_index=0):
    module = import_module(module_name)
    captured = []
    monkeypatch.setattr(module, "run_agent", lambda *args, **kwargs: result)
    monkeypatch.setattr(module, "assert_test", lambda case, metrics, **kwargs: captured.append((case, metrics)))
    kwargs = dict(
        case=module.CASES[case_index], model="invented-model", mcp=None,
        workspaces={"no-skill": "/invented"},
    )
    if module_name == "test_connection":
        module.test_connection(skill=None, **kwargs)
    else:
        module.test_task(**kwargs)
    return captured[0]


@pytest.mark.parametrize("module_name", ["test_tasks", "test_connection"])
def test_scenarios_preserve_unavailable_codex_cost(monkeypatch, module_name):
    result = parse_events([])
    case, _ = capture_scenario(monkeypatch, module_name, result)

    assert case.metadata["usage"]["costUsd"] is None
    assert case.token_cost is None
    assert case.model_dump(by_alias=True)["tokenCost"] is None


@pytest.mark.parametrize("scenario", ["missing", "wrong_date", "correct_date"])
def test_shift_requirements_reach_deepeval_as_scored_results(monkeypatch, scenario):
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    calls = [] if scenario == "missing" else [{
        "name": "list_shifts",
        "input": {"date": tomorrow if scenario == "correct_date" else "2000-01-01"},
        "output": "Invented shifts", "isError": False,
    }]
    result = {
        "answer": "Invented answer", "toolCalls": calls,
        "usage": {"inputTokens": 1, "outputTokens": 1, "costUsd": 0.01},
        "durationMs": 1, "turns": 1,
    }
    case, metrics = capture_scenario(monkeypatch, "test_tasks", result, case_index=1)
    metric = next((item for item in metrics if item.__name__ == "Shift Date"), None)

    assert metric is not None, "date failures must be recorded as a deterministic metric"
    assert metric.evaluation_model == "deterministic"
    assert metric.measure(case) == (1 if scenario == "correct_date" else 0)
    assert metric.is_successful() == (scenario == "correct_date")
    assert tomorrow in metric.reason
    assert len(case.tools_called) == len(calls)
    assert len(case._trace_dict["children"]) == len(calls)
    assert case.actual_output == "Invented answer"
