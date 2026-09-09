from datetime import date, timedelta
from importlib import import_module

import pytest

import conftest
from runners.codex import parse_events


def capture_scenario(monkeypatch, module_name, result, case_index=0, skill=None, repeat=1):
    module = import_module(module_name)
    captured = []
    monkeypatch.setattr(module, "run_agent", lambda *args, **kwargs: result)
    monkeypatch.setattr(module, "assert_test", lambda case, metrics, **kwargs: captured.append((case, metrics, kwargs)))
    kwargs = dict(
        case=module.CASES[case_index], model="invented-model", repeat=repeat, mcp=None,
        workspaces={"with-skill": "/with-skill", "no-skill": "/no-skill"},
    )
    if module_name == "test_connection":
        module.test_connection(skill=None, **kwargs)
    else:
        module.test_task(skill=skill, **kwargs)
    return captured[0]


def test_mcp_fixture_is_session_scoped():
    assert conftest.mcp._fixture_function_marker.scope == "session"


@pytest.mark.parametrize(("value", "expected"), [(None, 1), ("5", 5)])
def test_repeat_count_accepts_positive_integers(value, expected):
    assert conftest.repeat_count(value) == expected


@pytest.mark.parametrize("value", ["0", "-1", "no"])
def test_repeat_count_rejects_non_positive_integers(value):
    with pytest.raises(ValueError, match="^EVAL_REPEATS must be a positive integer$"):
        conftest.repeat_count(value)


@pytest.mark.parametrize("module_name", ["test_tasks", "test_connection"])
def test_scenarios_run_metrics_asynchronously(monkeypatch, module_name):
    result = {
        "answer": "Invented answer", "toolCalls": [],
        "usage": {"inputTokens": 1, "outputTokens": 1, "costUsd": 0.01},
        "durationMs": 1, "turns": 1,
    }

    _, _, assert_kwargs = capture_scenario(monkeypatch, module_name, result)

    assert assert_kwargs["run_async"] is True


@pytest.mark.parametrize(
    ("skill", "expected_variant"),
    [("shiftcare-mcp", "With skill"), (None, "No skill")],
)
def test_tasks_record_both_skill_variants(monkeypatch, skill, expected_variant):
    result = {
        "answer": "Invented answer", "toolCalls": [],
        "usage": {"inputTokens": 1, "outputTokens": 1, "costUsd": 0.01},
        "durationMs": 1, "turns": 1,
    }

    case, _, _ = capture_scenario(monkeypatch, "test_tasks", result, skill=skill)

    assert case.metadata["skillVariant"] == expected_variant


@pytest.mark.parametrize("module_name", ["test_tasks", "test_connection"])
def test_scenarios_record_repeat(monkeypatch, module_name):
    result = {
        "answer": "Invented answer", "toolCalls": [],
        "usage": {"inputTokens": 1, "outputTokens": 1, "costUsd": 0.01},
        "durationMs": 1, "turns": 1,
    }

    case, _, _ = capture_scenario(monkeypatch, module_name, result, repeat=5)

    assert case.metadata["repeat"] == 5


@pytest.mark.parametrize("module_name", ["test_tasks", "test_connection"])
def test_scenarios_preserve_unavailable_codex_cost(monkeypatch, module_name):
    result = parse_events([])
    case, _, _ = capture_scenario(monkeypatch, module_name, result)

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
    case, metrics, _ = capture_scenario(monkeypatch, "test_tasks", result, case_index=1)
    metric = next((item for item in metrics if item.__name__ == "Shift Date"), None)

    assert metric is not None, "date failures must be recorded as a deterministic metric"
    assert metric.evaluation_model == "deterministic"
    assert metric.measure(case) == (1 if scenario == "correct_date" else 0)
    assert metric.is_successful() == (scenario == "correct_date")
    assert tomorrow in metric.reason
    assert len(case.tools_called) == len(calls)
    assert len(case._trace_dict["children"]) == len(calls)
    assert case.actual_output == "Invented answer"
