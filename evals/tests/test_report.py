import datetime
import hashlib
import json
import os
import stat
from pathlib import Path

import pytest

import report
from report import main, normalize


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


def test_paired_differences_make_improvement_positive():
    pairs = [
        ({"metric_scores": {"Quality": 0.8}, "cost": 1}, {"metric_scores": {"Quality": 0.3}, "cost": 3}),
        ({"metric_scores": {"Quality": 0.4}, "cost": 4}, {"metric_scores": {"Quality": 0.6}, "cost": 2}),
    ]

    assert report.paired_differences(pairs, "metric:Quality") == pytest.approx([0.5, -0.2])
    assert report.paired_differences(pairs, "cost") == [2, -2]


def test_bootstrap_mean_interval_is_deterministic():
    interval = report.bootstrap_mean_interval([1, 2, 3, 4])

    assert interval == (1.5, 3.5)
    assert interval[0] <= 2.5 <= interval[1]
    assert report.bootstrap_mean_interval([]) == (None, None)
    assert report.bootstrap_mean_interval([1]) == (None, None)


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


def test_report_pairs_repeats_independently(tmp_path):
    run = invented_run()
    first_pair = run["testCases"][:2]
    second_pair = json.loads(json.dumps(first_pair))
    for result in first_pair:
        result["metadata"]["repeat"] = 1
    for result in second_pair:
        result["metadata"]["repeat"] = 2
    second_pair[0]["metadata"]["usage"]["totalTokens"] = 300
    second_pair[1]["metadata"]["usage"]["totalTokens"] = 150
    run["testCases"] = first_pair + second_pair

    _, _, page = write_report(tmp_path, run)
    visible = visible_html(page)
    detail = visible.split('id="case-panel-c1"', 1)[1]

    assert "<strong>2</strong> paired comparisons" in visible
    assert "2 paired model comparisons" in detail
    assert "invented-model · repeat 1" in visible
    assert "invented-model · repeat 2" in visible
    assert "100 / 200" in detail
    assert "300 / 150" in detail


def test_normalize_defaults_legacy_results_to_repeat_one():
    results, _ = normalize(invented_run()["testCases"])

    assert {result["repeat"] for result in results} == {1}


def test_report_summarizes_repeated_quality_before_overhead(tmp_path):
    run = invented_run()
    base_pair = run["testCases"][:2]
    results = []
    for repeat, (with_score, without_score) in enumerate(
        [(0.8, 0.4), (0.3, 0.5), (0.5, 0.5), (1.0, 0.4)], 1
    ):
        pair = json.loads(json.dumps(base_pair))
        for result, score in zip(pair, (with_score, without_score)):
            result["metadata"]["repeat"] = repeat
            result["metricsData"][0]["score"] = score
        results.extend(pair)
    run["testCases"] = results
    for result in results:
        result["metricsData"].append(
            {"name": "Invented future metric", "score": 0.7, "success": True}
        )

    _, _, page = write_report(tmp_path, run)
    detail = visible_html(page).split('id="case-panel-c1"', 1)[1]
    quality = detail.split("<h2>Quality</h2>", 1)[1].split("<h2>Overhead</h2>", 1)[0]
    overhead = detail.split("<h2>Overhead</h2>", 1)[1].split(
        "<h2>Per-model comparisons</h2>", 1
    )[0]

    assert detail.index("<h2>Quality</h2>") < detail.index("<h2>Overhead</h2>")
    assert "Invented future metric" in quality
    assert "Invented future metric" not in overhead
    assert "2 wins / 1 tie / 1 loss" in quality
    assert "0.20" in quality
    assert "n=4" in quality
    assert "95% interval" in quality
    assert "scenario/model sample" in detail
    assert "multiple-comparison" in detail


def test_report_does_not_colour_increased_overhead_as_quality_regression(tmp_path):
    run = invented_run()
    run["testCases"][0]["metadata"]["usage"]["totalTokens"] = 300

    _, _, page = write_report(tmp_path, run)
    comparisons = visible_html(page).split("<h2>Case comparisons</h2>", 1)[1]
    overview_row = comparisons.split("<tr><td>", 1)[1].split("</tr>", 1)[0]

    assert '<td class="overhead"><strong>1.5× more</strong><small>300 / 200</small></td>' in overview_row


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


@pytest.mark.parametrize("complete_pair", [False, True])
def test_report_aggregates_only_pairs_with_both_measure_values(tmp_path, complete_pair):
    run = invented_run()
    first_pair = run["testCases"][:2]
    second_pair = json.loads(json.dumps(first_pair))
    for result in second_pair:
        result["metadata"]["model"] = "invented-second-model"
    run["testCases"] = first_pair + second_pair
    for result, value in zip(run["testCases"], [None, 0.2, 0.8, None]):
        result["metricsData"][0]["score"] = value
        result["tokenCost"] = value
        result["metadata"]["usage"]["costUsd"] = value
    if complete_pair:
        third_pair = json.loads(json.dumps(first_pair))
        for result, value in zip(third_pair, [0.6, 0.3]):
            result["metadata"]["model"] = "invented-third-model"
            result["metricsData"][0]["score"] = value
            result["tokenCost"] = value
            result["metadata"]["usage"]["costUsd"] = value
        run["testCases"].extend(third_pair)

    _, _, page = write_report(tmp_path, run)
    aggregate = visible_html(page).split("<h2>Aggregate impact</h2>", 1)[1].split(
        "<h2>Per-model comparisons</h2>", 1
    )[0]

    if complete_pair:
        assert '<strong>2.0× better</strong><small>0.60 / 0.30</small>' in aggregate
        assert '<td>Response quality</td><td>0.60</td><td>0.30</td><td>2.0× better</td>' in aggregate
        assert '<strong>2.0× higher</strong><small>$0.6 / $0.3</small>' in aggregate
        assert '<td>Estimated cost</td><td>$0.6</td><td>$0.3</td><td>2.0× higher</td>' in aggregate
    else:
        assert '<span>Response quality</span><strong>comparison unavailable</strong><small>— / —</small>' in aggregate
        assert '<td>Response quality</td><td>—</td><td>—</td><td>comparison unavailable</td>' in aggregate
        assert '<span>Estimated cost</span><strong>comparison unavailable</strong><small>— / —</small>' in aggregate
        assert '<td>Estimated cost</td><td>—</td><td>—</td><td>comparison unavailable</td>' in aggregate
    assert '<strong>2.0× fewer</strong><small>100 / 200</small>' in aggregate


@pytest.mark.parametrize("existing", [False, True])
def test_report_is_private_before_any_content_is_written(tmp_path, monkeypatch, existing):
    output = tmp_path / "report.html"
    if existing:
        output.write_text("Previous invented report")
        output.chmod(0o644)
    writes = []

    class ObservedOutput:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def fileno(self):
            return self.stream.fileno()

        def write(self, content):
            mode = stat.S_IMODE(os.fstat(self.fileno()).st_mode)
            assert mode == 0o600, f"report content was written with mode {mode:04o}"
            writes.append(content)
            return self.stream.write(content)

    original_path_open = Path.open
    original_fdopen = os.fdopen

    def observe_path_open(path, mode="r", *args, **kwargs):
        stream = original_path_open(path, mode, *args, **kwargs)
        return ObservedOutput(stream) if path == output and "w" in mode else stream

    monkeypatch.setattr(Path, "open", observe_path_open)
    monkeypatch.setattr(os, "fdopen", lambda *args, **kwargs: ObservedOutput(original_fdopen(*args, **kwargs)))
    old_umask = os.umask(0o022)
    try:
        write_report(tmp_path, invented_run())
    finally:
        os.umask(old_umask)
    assert len(writes) == 1


def test_default_output_is_a_named_run_under_reports(tmp_path, monkeypatch):
    source = tmp_path / "run.json"
    source.write_text(json.dumps({"testCases": []}))
    os.utime(source, (1757000000, 1757000000))
    monkeypatch.chdir(tmp_path)

    report.main([str(source)])

    expected = datetime.datetime.fromtimestamp(1757000000).astimezone().strftime("%Y-%m-%d-%H%M%S")
    written = list((tmp_path / "reports").glob("*.html"))
    assert [path.name for path in written] == [f"{expected}.html"]


def test_report_writes_to_the_named_run_path(tmp_path, monkeypatch):
    source = tmp_path / "run.json"
    source.write_text(json.dumps({"testCases": []}))
    monkeypatch.chdir(tmp_path)

    report.main([str(source)])

    written = list((tmp_path / "reports").glob("*.html"))
    assert len(written) == 1
    assert written[0].stat().st_mode & 0o777 == 0o600


def test_current_tree_hashes_are_stable_and_include_all_skill_files(tmp_path):
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "z.txt").write_text("invented z")
    nested = skill / "nested"
    nested.mkdir()
    (nested / "a.txt").write_text("invented a")
    digest = hashlib.sha256()
    for relative, content in (
        ("nested/a.txt", b"invented a"),
        ("z.txt", b"invented z"),
    ):
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")

    scenario = tmp_path / "scenario.py"
    scenario.write_text('CASES = [{"quality": "invented", "name": "case"}]\n')
    canonical = b'[{"name":"case","quality":"invented"}]'

    assert report.directory_hash(skill) == digest.hexdigest()[:12]
    assert report.cases_hash(scenario) == hashlib.sha256(canonical).hexdigest()[:12]


def test_report_rolls_up_matrix_and_suite_without_cross_case_pair_collisions(tmp_path):
    run = invented_run()
    first_pair = run["testCases"][:2]
    second_pair = json.loads(json.dumps(first_pair))
    for result, score in zip(second_pair, (0.2, 0.8)):
        result["metadata"].update({"case": "invented second case"})
        result["metricsData"][0]["score"] = score
    run["testCases"] = first_pair + second_pair

    _, _, page = write_report(tmp_path, run)
    rollup = visible_html(page).split('id="rollup-performance"', 1)[1].split(
        "<h2>Case comparisons</h2>", 1
    )[0]

    assert "Whole matrix" in rollup
    assert "Connection verification" in rollup
    assert "2 / 2 (100.0%)" in rollup
    assert "0 / 2 (0.0%)" in rollup
    assert "<td>-0.10</td>" in rollup
    assert "<td>n=2</td>" in rollup


def test_report_shows_case_samples_current_tree_hashes_and_low_sample_warning(tmp_path):
    _, _, page = write_report(tmp_path, invented_run())
    detail = visible_html(page).split('id="case-panel-c1"', 1)[1].split(
        'id="case-panel-c2"', 1
    )[0]

    assert "Samples and current-tree provenance" in detail
    assert "invented-model · With skill: <strong>n=1</strong>" in detail
    assert "invented-model · No skill: <strong>n=1</strong>" in detail
    assert "Low sample count:" in detail
    assert "skill_hash=" in detail and "scenario_hash=" in detail
    assert "cannot be verified against them" in detail


def test_all_tables_contain_pathological_reasons_at_narrow_width(tmp_path):
    run = invented_run()
    run["testCases"][0]["metricsData"][0]["reason"] = "x" * 10_000

    _, _, page = write_report(tmp_path, run)
    visible = visible_html(page)

    assert '<div class="matrix-wrap"><table class="metrics result-metrics">' in visible
    assert '<th class="reason">Reason</th>' in visible
    assert '<td class="reason">' + "x" * 10_000 in visible
    assert ".reason{width:40rem;max-width:40rem;white-space:normal;overflow-wrap:anywhere}" in visible
    assert visible.count("<table") == visible.count('<div class="matrix-wrap"><table')


def test_report_pools_every_archived_run_by_default(tmp_path, monkeypatch):
    # The point of pooling: a narrow run adds samples to a case instead of
    # replacing the matrix, so a case's n grows as runs accumulate.
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "2026-01-01-000000.json").write_text(json.dumps(invented_run()))
    (runs / "2026-01-02-000000.json").write_text(json.dumps(invented_run()))
    monkeypatch.chdir(tmp_path)

    report.main([])

    page = next((tmp_path / "reports").glob("*.html")).read_text()
    visible = visible_html(page)
    assert "these 2 runs combined, totalling 6 results" in visible
    assert "2026-01-01-000000.json" in visible
    assert "2026-01-02-000000.json" in visible


def test_report_falls_back_to_the_deepeval_run_when_nothing_is_archived(tmp_path, monkeypatch):
    source = tmp_path / report.DEFAULT_INPUT
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps(invented_run()))
    monkeypatch.chdir(tmp_path)

    report.main([])

    assert len(list((tmp_path / "reports").glob("*.html"))) == 1


def test_pooled_results_keep_distinct_ids_across_files(tmp_path, monkeypatch):
    # normalize() numbers results with a running counter, so pooling has to run
    # it once over the concatenated results rather than once per file.
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "a.json").write_text(json.dumps(invented_run()))
    (runs / "b.json").write_text(json.dumps(invented_run()))
    monkeypatch.chdir(tmp_path)

    report.main([])

    page = next((tmp_path / "reports").glob("*.html")).read_text()
    assert 'id="result-r6"' in visible_html(page).lower() or "R6" in visible_html(page)
