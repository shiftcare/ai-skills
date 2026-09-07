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


def test_report_renders_comparisons_and_drilldown(tmp_path):
    _, _, page = write_report(tmp_path, invented_run())

    assert "Overview" in page
    assert "All results" in page
    assert "Case detail" in page
    assert "Check the invented account &lt;carefully&gt;." in page
    assert 'id="suite-s1"' in page and ">S1<" in page
    assert 'id="case-c1"' in page and ">C1<" in page
    assert 'id="result-r1"' in page and ">R1<" in page
    for reason in (
        "Skill answer is grounded",
        "With skill tool reason",
        "Baseline answer missed evidence",
        "No skill tool reason",
        "Unpaired result passed",
    ):
        assert reason in page
    assert "whoami" in page
    assert '&quot;scope&quot;: &quot;With skill&quot;' in page
    assert '&quot;account&quot;: &quot;Invented Care&quot;' in page
    assert "Final With skill answer" in page
    assert "2.0× fewer" in page
    assert "100 / 200" in page
    assert "comparison unavailable" in page
    assert "Results saved" in page
    assert "2000" in page


def test_report_accepts_wrapped_json_and_escapes_dynamic_content(tmp_path):
    run = invented_run()
    attack = "<script>alert(1)</script>"
    run["testCases"][0]["actualOutput"] = attack
    _, _, page = write_report(tmp_path, {"testRunData": run})

    assert attack not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
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

    assert "Connection verification" in page
    assert "Read-only tasks" in page
    assert "connect and verify" in page
    assert "client lookup picks list_clients" in page
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
