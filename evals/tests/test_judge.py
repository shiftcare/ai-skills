import importlib

import pytest

import judge


def test_judge_model_can_be_overridden(monkeypatch):
    monkeypatch.setenv("EVAL_JUDGE_MODEL", "gpt-5.6-luna")
    monkeypatch.setattr(
        judge,
        "run_agent",
        lambda prompt, model, cwd, skill, mcp: {"answer": f"{model}: {prompt}"},
    )

    evaluator = judge.ClaudeJudge({"no-skill": "/tmp/invented-workspace"})

    assert evaluator.generate("Invented prompt") == "gpt-5.6-luna: Invented prompt"
    assert evaluator.get_model_name() == "Codex CLI (gpt-5.6-luna)"


@pytest.mark.parametrize(("value", "expected"), [(None, 4), ("2", 2)])
def test_judge_concurrency(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("EVAL_JUDGE_CONCURRENCY", raising=False)
    else:
        monkeypatch.setenv("EVAL_JUDGE_CONCURRENCY", value)

    reloaded = importlib.reload(judge)

    assert reloaded._JUDGE_SLOTS._value == expected
