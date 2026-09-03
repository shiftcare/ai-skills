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
