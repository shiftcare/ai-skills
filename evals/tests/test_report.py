import json
import os
import stat

from report import main


def invented_run():
    def result(name, variant, success, tokens, quality, reason):
        return {
            "name": name,
            "input": "Check the invented account <carefully>.",
            "actualOutput": f"Final {variant} answer",
            "toolsCalled": [
                {
                    "name": "whoami",
                    "inputParameters": {"scope": variant},
                    "output": {"account": "Invented Care"},
                }
            ],
            "metricsData": [
                {
                    "name": "Response quality",
                    "score": quality,
                    "threshold": 0.5,
                    "success": success,
                    "reason": reason,
                },
                {
                    "name": "Tool correctness",
                    "score": 1 if success else 0,
                    "threshold": 1,
                    "success": success,
                    "reason": f"{variant} tool reason",
                },
            ],
            "success": success,
            "tokenCost": tokens / 100_000,
            "completionTime": 3 if variant == "With skill" else 6,
            "metadata": {
                "suite": "Connection verification",
                "case": "connect and verify",
                "model": "invented-model",
                "skillVariant": variant,
                "usage": {
                    "inputTokens": tokens - 10,
                    "outputTokens": 10,
                    "totalTokens": tokens,
                    "costUsd": tokens / 100_000,
                },
                "durationMs": 3000 if variant == "With skill" else 6000,
                "turns": 2 if variant == "With skill" else 4,
                "toolCallCount": 1,
            },
        }

    with_skill = result(
        "legacy-model / shiftcare-mcp: legacy case",
        "With skill",
        True,
        100,
        0.8,
        "Skill answer is grounded",
    )
    no_skill = result(
        "legacy-model / no skill: legacy case",
        "No skill",
        False,
        200,
        0.4,
        "Baseline answer missed evidence",
    )
    unpaired = result(
        "second-model / shiftcare-mcp: account and write access",
        "With skill",
        True,
        120,
        0.7,
        "Unpaired result passed",
    )
    unpaired["metadata"].update(
        {"case": "account and write access", "model": "second-model"}
    )
    return {"testCases": [with_skill, no_skill, unpaired]}


def write_report(tmp_path, run):
    source = tmp_path / "run.json"
    output = tmp_path / "report.html"
    source.write_text(json.dumps(run))
    os.utime(source, (962_452_800, 962_452_800))
    main([str(source), "-o", str(output)])
    return source, output, output.read_text()


def visible_html(page):
    return page.split('<script type="application/json" id="source-data">', 1)[0]


def test_report_renders_comparisons_and_drilldown(tmp_path):
    _, _, page = write_report(tmp_path, invented_run())
    visible = visible_html(page)

    assert "Overview" in visible
    assert "All results" in visible
    assert "Case detail" in visible
    assert "Check the invented account &lt;carefully&gt;." in visible
    assert 'id="suite-s1"' in visible and ">S1<" in visible
    assert 'id="case-c1"' in visible and ">C1<" in visible
    assert 'id="result-r1"' in visible and ">R1<" in visible
    for reason in (
        "Skill answer is grounded",
        "With skill tool reason",
        "Baseline answer missed evidence",
        "No skill tool reason",
        "Unpaired result passed",
    ):
        assert reason in visible
    assert "whoami" in visible
    assert '&quot;scope&quot;: &quot;With skill&quot;' in visible
    assert '&quot;account&quot;: &quot;Invented Care&quot;' in visible
    assert "Final With skill answer" in visible
    assert "2.0× fewer" in visible
    assert "100 / 200" in visible
    assert "comparison unavailable" in visible
    assert "Results saved" in visible
    assert "2000" in visible


def test_report_renders_unavailable_rows_for_models_in_mixed_case(tmp_path):
    run = invented_run()
    mixed = json.loads(json.dumps(run["testCases"][2]))
    mixed["name"] = "mixed-unpaired-model / shiftcare-mcp: connect and verify"
    mixed["metadata"].update(
        {"case": "connect and verify", "model": "mixed-unpaired-model"}
    )
    run["testCases"].append(mixed)

    _, _, page = write_report(tmp_path, run)
    visible = visible_html(page)
    overview_case = visible.split('href="#case-c1"', 1)[1].split(
        'href="#case-c2"', 1
    )[0]
    detail_case = visible.split('id="case-panel-c1"', 1)[1].split(
        'id="case-panel-c2"', 1
    )[0]
    per_model = detail_case.split("<h2>Per-model comparisons</h2>", 1)[1].split(
        "<h2>Scenario results</h2>", 1
    )[0]

    assert "mixed-unpaired-model" in overview_case
    assert "comparison unavailable" in overview_case
    assert "mixed-unpaired-model" in per_model
    assert "comparison unavailable" in per_model


def test_report_uses_measure_words_for_zero_values_and_shows_card_values(tmp_path):
    run = invented_run()
    with_skill = run["testCases"][0]
    with_skill["tokenCost"] = 0
    with_skill["metadata"]["durationMs"] = 0
    with_skill["metadata"]["toolCallCount"] = 0

    _, _, page = write_report(tmp_path, run)
    visible = visible_html(page)
    overview_case = visible.split('href="#case-c1"', 1)[1].split(
        'href="#case-c2"', 1
    )[0]
    detail_case = visible.split('id="case-panel-c1"', 1)[1].split(
        'id="case-panel-c2"', 1
    )[0]
    impact = detail_case.split('<div class="impact-grid">', 1)[1].split(
        "<h2>All metric changes</h2>", 1
    )[0]

    assert '<strong>better</strong><small>1.00 / 0.00</small>' in overview_case
    assert '<strong>lower</strong><small>$0 / $0.002</small>' in overview_case
    assert '<strong>faster</strong><small>0.0s / 6.0s</small>' in overview_case
    assert '<strong>fewer</strong><small>0 / 1</small>' in overview_case
    assert "Estimated cost" in impact
    assert "lower" in impact
    assert "$0 / $0.002" in impact


def test_report_accepts_wrapped_json_and_escapes_dynamic_content(tmp_path):
    run = invented_run()
    attack = "<script>alert(1)</script>"
    run["testCases"][0]["actualOutput"] = attack
    _, _, page = write_report(tmp_path, {"testRunData": run})
    visible = visible_html(page)

    assert attack not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in visible
    source_json = page.split('<script type="application/json" id="source-data">', 1)[1].split(
        "</script>", 1
    )[0]
    assert "<" not in source_json
    assert "\\u003cscript\\u003e" in source_json


def test_report_uses_legacy_names_and_writes_private_file(tmp_path):
    run = invented_run()
    for test_case in run["testCases"]:
        test_case.pop("metadata")
    run["testCases"][0]["name"] = "legacy-model / shiftcare-mcp: connect and verify"
    run["testCases"][1]["name"] = "legacy-model / no skill: connect and verify"
    run["testCases"][2]["name"] = "second-model: client lookup picks list_clients"

    _, output, page = write_report(tmp_path, run)
    visible = visible_html(page)

    assert "Connection verification" in visible
    assert "Read-only tasks" in visible
    assert "connect and verify" in visible
    assert "client lookup picks list_clients" in visible
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
