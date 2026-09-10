from datetime import date, timedelta
from importlib import import_module
from pathlib import Path

import pytest

import conftest
import identity
import scenario
from runners.codex import parse_events


DISCOVERED_SUITES = identity.suites()
SUITE_PARAMS = list(DISCOVERED_SUITES.items())


def capture_scenario(monkeypatch, suite_name, result, case_index=0, skill=None):
    spec = DISCOVERED_SUITES[suite_name]
    module = import_module(spec["file"].stem)
    captured = []
    target = module if spec["file"].name == "test_connection.py" else scenario
    monkeypatch.setattr(target, "run_agent", lambda *args, **kwargs: result)
    monkeypatch.setattr(
        target,
        "assert_test",
        lambda case, metrics, **kwargs: captured.append((case, metrics, kwargs)),
    )
    kwargs = dict(
        case=module.CASES[case_index],
        model="invented-model",
        mcp=None,
        workspaces={
            "no-skill": "/no-skill",
            "home": "/home",
            "skills": {spec["skill"]: "/with-skill"},
        },
    )
    if spec["file"].name == "test_connection.py":
        module.test_connection(skill=skill, **kwargs)
    else:
        module.test_scenario(skill=skill, **kwargs)
    return captured[0]


def invented_result(tool_calls=None):
    return {
        "answer": "Invented answer",
        "toolCalls": tool_calls or [],
        "usage": {"inputTokens": 1, "outputTokens": 1, "costUsd": 0.01},
        "durationMs": 1,
        "turns": 1,
    }


def test_mcp_fixture_resolves_per_test():
    """MCP tokens live 300 seconds. A session-scoped fixture resolves once per
    xdist worker and then reuses an expired token for the rest of a long run,
    which silently strips every agent's ShiftCare tools. Resolve per test:
    `auth.mjs token` reuses a token with more than 30 seconds left, so the
    cost is one subprocess call, not an OAuth round trip."""
    assert conftest.mcp._fixture_function_marker.scope == "function"


@pytest.mark.parametrize(("suite_name", "spec"), SUITE_PARAMS, ids=DISCOVERED_SUITES)
def test_scenarios_run_metrics_asynchronously(monkeypatch, suite_name, spec):
    _, _, assert_kwargs = capture_scenario(
        monkeypatch, suite_name, invented_result()
    )

    assert assert_kwargs["run_async"] is True


@pytest.mark.parametrize(("suite_name", "spec"), SUITE_PARAMS, ids=DISCOVERED_SUITES)
@pytest.mark.parametrize(
    ("with_skill", "expected_variant"),
    [(True, "With skill"), (False, "No skill")],
)
def test_scenarios_record_both_skill_variants(
    monkeypatch, suite_name, spec, with_skill, expected_variant
):
    skill = spec["skill"] if with_skill else None

    case, _, _ = capture_scenario(
        monkeypatch, suite_name, invented_result(), skill=skill
    )

    assert case.metadata["skillVariant"] == expected_variant


def test_client_lookup_case_is_bounded():
    case = import_module("test_tasks").CASES[0]

    assert case == {
        "name": "client lookup returns up to five active clients",
        "ask": "Name up to five active clients.",
        "expected_tools": ["list_clients"],
        "quality": (
            "Names no more than five real active clients from the account; does not "
            "fabricate clients or claim it has no access."
        ),
        "activates": False,
    }


@pytest.mark.parametrize(
    ("skill", "expected_count"),
    [("shiftcare-mcp", 1), (None, 0)],
)
def test_tasks_score_skill_non_activation_only_with_installed_skill(
    monkeypatch, skill, expected_count
):
    case, metrics, _ = capture_scenario(
        monkeypatch, "Read-only tasks", invented_result(), skill=skill
    )
    activation_metrics = [
        metric for metric in metrics if metric.__name__ == "Skill Activation"
    ]

    assert len(activation_metrics) == expected_count
    if activation_metrics:
        assert activation_metrics[0].measure(case) == 1


def evaluate_case(monkeypatch, case, skill="shiftcare-mcp"):
    captured = []
    monkeypatch.setattr(scenario, "run_agent", lambda *args, **kwargs: invented_result())
    monkeypatch.setattr(scenario, "assert_test", lambda test_case, metrics, **kwargs: captured.append(metrics))
    workspaces = {"no-skill": "/no-skill", "home": "/home", "skills": {skill: "/with-skill"}}
    scenario.evaluate(case, skill, "invented-model", None, workspaces, "Invented suite", Path("test_tasks.py"))
    return {metric.__name__: metric for metric in captured[0]}


def test_activates_none_opts_a_case_out_of_activation_scoring(monkeypatch):
    """A boundary case such as "move this shift" with cancel-shift installed is
    right whether the skill loads and refuses or never loads, so it must not be
    scored on activation either way."""
    case = {"name": "boundary", "ask": "Move it", "expected_tools": ["list_shifts"], "quality": "Declines.", "activates": None}

    assert "Skill Activation" not in evaluate_case(monkeypatch, case)


def test_shift_date_is_opt_in_and_relative_to_today(monkeypatch):
    """Not every list_shifts case pins one day: a daily rundown spans yesterday
    and today, so the date check applies only when a case names the day."""
    base = {"name": "shifts", "ask": "Shifts?", "expected_tools": ["list_shifts"], "quality": "Real shifts."}

    assert "Shift Date" not in evaluate_case(monkeypatch, base)
    metric = evaluate_case(monkeypatch, {**base, "shift_date": "yesterday"})["Shift Date"]
    assert metric.expected_date == (date.today() - timedelta(days=1)).isoformat()


def test_team_lookup_case_is_bounded():
    assert {
        "name": "team lookup returns up to five teams",
        "ask": "Name up to five ShiftCare teams.",
        "expected_tools": ["list_teams"],
        "quality": "Names no more than five real teams and does not fabricate teams.",
        "activates": False,
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

    case, metrics, _ = capture_scenario(
        monkeypatch,
        "Connection verification",
        invented_result(),
        case_index=case_index,
    )

    assert [tool.name for tool in case.expected_tools] == ["whoami"]
    assert all(metric.__name__ != "Connection Protocol" for metric in metrics)


@pytest.mark.parametrize(("suite_name", "spec"), SUITE_PARAMS, ids=DISCOVERED_SUITES)
@pytest.mark.parametrize("with_skill", [True, False])
def test_scenarios_record_content_hashes(
    monkeypatch, suite_name, spec, with_skill
):
    skill = spec["skill"] if with_skill else None

    case, _, _ = capture_scenario(
        monkeypatch, suite_name, invented_result(), skill=skill
    )

    assert case.metadata["scenarioHash"] == identity.cases_hash(spec["file"])
    if skill:
        assert case.metadata["skillHash"] == identity.skill_hash(skill)
    else:
        # The no-skill arm has no skill to hash; a real hash there would split
        # every pair, since the arms would never share an identity.
        assert case.metadata["skillHash"] == identity.NO_SKILL


@pytest.mark.parametrize(("suite_name", "spec"), SUITE_PARAMS, ids=DISCOVERED_SUITES)
def test_scenarios_preserve_unavailable_codex_cost(monkeypatch, suite_name, spec):
    case, _, _ = capture_scenario(
        monkeypatch, suite_name, parse_events([])
    )

    assert case.metadata["usage"]["costUsd"] is None
    assert case.token_cost is None
    assert case.model_dump(by_alias=True)["tokenCost"] is None


def test_discovered_suites_are_structurally_valid():
    suite_names = []
    for suite_name, spec in DISCOVERED_SUITES.items():
        module = import_module(spec["file"].stem)
        names = []
        suite_names.append(module.SUITE)
        assert module.SUITE == suite_name
        assert module.SKILL == spec["skill"]
        assert (identity.PROJECT_ROOT / "skills" / module.SKILL).is_dir()
        for case in module.CASES:
            assert {"name", "ask", "expected_tools", "quality"} <= case.keys()
            assert isinstance(case["expected_tools"], list)
            assert case["expected_tools"]
            names.append(case["name"])
        assert len(names) == len(set(names))
    assert len(suite_names) == len(set(suite_names))


@pytest.mark.parametrize("scenario_name", ["missing", "wrong_date", "correct_date"])
def test_shift_requirements_reach_deepeval_as_scored_results(
    monkeypatch, scenario_name
):
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    calls = (
        []
        if scenario_name == "missing"
        else [
            {
                "name": "list_shifts",
                "input": {
                    "date": tomorrow if scenario_name == "correct_date" else "2000-01-01"
                },
                "output": "Invented shifts",
                "isError": False,
            }
        ]
    )
    case, metrics, _ = capture_scenario(
        monkeypatch,
        "Read-only tasks",
        invented_result(calls),
        case_index=1,
    )
    metric = next((item for item in metrics if item.__name__ == "Shift Date"), None)

    assert metric is not None, "date failures must be recorded as a deterministic metric"
    assert metric.evaluation_model == "deterministic"
    assert metric.measure(case) == (1 if scenario_name == "correct_date" else 0)
    assert metric.is_successful() == (scenario_name == "correct_date")
    assert tomorrow in metric.reason
    assert len(case.tools_called) == len(calls)
    assert len(case._trace_dict["children"]) == len(calls)
    assert case.actual_output == "Invented answer"


@pytest.mark.parametrize(
    ("skill", "expected_count"),
    [("shiftcare-mcp", 1), (None, 0)],
)
def test_connection_protocol_scored_only_with_installed_skill(
    monkeypatch, skill, expected_count
):
    """ConnectionProtocol checks the Verify protocol only SKILL.md teaches, so the
    no-skill arm must not be scored on it. All 20 no-skill results failed it in the
    2026-09-10 matrix, 9 while answering well enough to pass Response quality."""
    result = invented_result(
        [{"name": "whoami", "input": {}, "output": "Invented account"}]
    )

    _, metrics, _ = capture_scenario(
        monkeypatch, "Connection verification", result, skill=skill
    )

    protocol = [
        metric for metric in metrics if metric.__name__ == "Connection Protocol"
    ]
    assert len(protocol) == expected_count
