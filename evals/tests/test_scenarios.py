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


def test_mcp_fixture_resolves_per_test():
    """MCP tokens live 300 seconds. A session-scoped fixture resolves once per
    xdist worker and then reuses an expired token for the rest of a long run,
    which silently strips every agent's ShiftCare tools. Resolve per test:
    `auth.mjs token` reuses a token with more than 30 seconds left, so the
    cost is one subprocess call, not an OAuth round trip."""
    assert conftest.mcp._fixture_function_marker.scope == "function"


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


def test_client_lookup_case_is_bounded():
    case = import_module("test_tasks").CASES[0]

    assert case == {
        "name": "client lookup returns up to five active clients",
        "ask": "Name up to five active clients.",
        "expected_tool": "list_clients",
        "quality": (
            "Names no more than five real active clients from the account; does not "
            "fabricate clients or claim it has no access."
        ),
    }


@pytest.mark.parametrize(
    ("skill", "expected_count"),
    [("shiftcare-mcp", 1), (None, 0)],
)
def test_tasks_score_skill_non_activation_only_with_installed_skill(
    monkeypatch, skill, expected_count
):
    result = {
        "answer": "Invented answer", "toolCalls": [],
        "usage": {"inputTokens": 1, "outputTokens": 1, "costUsd": 0.01},
        "durationMs": 1, "turns": 1,
    }

    case, metrics, _ = capture_scenario(monkeypatch, "test_tasks", result, skill=skill)
    activation_metrics = [metric for metric in metrics if metric.__name__ == "Skill Activation"]

    assert len(activation_metrics) == expected_count
    if activation_metrics:
        assert activation_metrics[0].measure(case) == 1


def test_team_lookup_case_is_bounded():
    assert {
        "name": "team lookup returns up to five teams",
        "ask": "Name up to five ShiftCare teams.",
        "expected_tool": "list_teams",
        "quality": "Names no more than five real teams and does not fabricate teams.",
    } in import_module("test_tasks").CASES


def test_account_identity_uses_whoami_without_connection_protocol(monkeypatch):
    module = import_module("test_connection")
    expected_case = {
        "name": "account identity uses whoami without connection verification",
        "ask": "What ShiftCare account am I signed into?",
        "expected_tools": ["whoami"],
        "quality": "Names the signed-in account from whoami and does not invent access details.",
    }
    case_index = module.CASES.index(expected_case)
    result = {
        "answer": "Invented account", "toolCalls": [],
        "usage": {"inputTokens": 1, "outputTokens": 1, "costUsd": 0.01},
        "durationMs": 1, "turns": 1,
    }

    case, metrics, _ = capture_scenario(
        monkeypatch, "test_connection", result, case_index=case_index
    )

    assert [tool.name for tool in case.expected_tools] == ["whoami"]
    assert all(metric.__name__ != "Connection Protocol" for metric in metrics)


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
