import argparse
import datetime
import html
import json
import os
import pathlib
import statistics


DEFAULT_INPUT = ".deepeval/.latest_run_full.json"
DEFAULT_OUTPUT = ".deepeval/report.html"


def escape(value):
    return html.escape(str(value), quote=True)


def pretty(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, indent=2, ensure_ascii=False)
    if value is None:
        return "Unavailable"
    return str(value)


def first(mapping, *keys, default=None):
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return default


def legacy_identity(name):
    for marker, variant in (
        (" / shiftcare-mcp: ", "With skill"),
        (" / no skill: ", "No skill"),
    ):
        if marker in name:
            model, case = name.split(marker, 1)
            return "Connection verification", case, model, variant
    if ": " in name:
        model, case = name.split(": ", 1)
        return "Read-only tasks", case, model, "No skill"
    return "Unclassified", name, "Unknown model", "No skill"


def normalize(source):
    run = source.get("testRunData", source) if isinstance(source, dict) else {}
    raw_results = first(run, "testCases", "test_cases", "testResults", default=[])
    results = []
    suite_ids = {}
    case_ids = {}
    for raw in raw_results:
        name = str(raw.get("name", "Unnamed result"))
        legacy_suite, legacy_case, legacy_model, legacy_variant = legacy_identity(name)
        metadata = first(
            raw,
            "additional_metadata",
            "additionalMetadata",
            "metadata",
            default={},
        )
        suite = metadata.get("suite", legacy_suite)
        case = metadata.get("case", legacy_case)
        model = metadata.get("model", legacy_model)
        variant = metadata.get("skillVariant", legacy_variant)
        suite_ids.setdefault(suite, f"S{len(suite_ids) + 1}")
        case_ids.setdefault((suite, case), f"C{len(case_ids) + 1}")
        usage = metadata.get("usage") or {}
        input_tokens = first(usage, "inputTokens", "input_tokens")
        output_tokens = first(usage, "outputTokens", "output_tokens")
        total_tokens = first(usage, "totalTokens", "total_tokens")
        if total_tokens is None and input_tokens is not None and output_tokens is not None:
            total_tokens = input_tokens + output_tokens
        tools = first(raw, "toolsCalled", "tools_called", default=[]) or []
        duration_ms = first(metadata, "durationMs", "duration_ms")
        if duration_ms is None and raw.get("completionTime") is not None:
            duration_ms = raw["completionTime"] * 1000
        result = {
            "raw": raw,
            "id": f"R{len(results) + 1}",
            "suite_id": suite_ids[suite],
            "case_id": case_ids[(suite, case)],
            "suite": suite,
            "case": case,
            "model": model,
            "variant": variant,
            "input": first(raw, "input", default="Unavailable"),
            "output": first(raw, "actualOutput", "actual_output", default="Unavailable"),
            "success": bool(raw.get("success")),
            "metrics": first(raw, "metricsData", "metrics_data", default=[]) or [],
            "tools": tools,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "tokens": total_tokens,
            "cost": first(raw, "tokenCost", default=usage.get("costUsd")),
            "duration_ms": duration_ms,
            "turns": metadata.get("turns"),
            "tool_calls": first(metadata, "toolCallCount", "tool_call_count", default=len(tools)),
        }
        result["metric_scores"] = {
            str(metric.get("name", "Unnamed metric")): metric.get("score")
            for metric in result["metrics"]
        }
        results.append(result)
    suites = []
    for suite, suite_id in suite_ids.items():
        cases = []
        for (case_suite, case), case_id in case_ids.items():
            if case_suite == suite:
                cases.append(
                    {
                        "id": case_id,
                        "name": case,
                        "results": [
                            result
                            for result in results
                            if result["suite"] == suite and result["case"] == case
                        ],
                    }
                )
        suites.append({"id": suite_id, "name": suite, "cases": cases})
    return run, results, suites


def pairs_for(results):
    return [
        (with_skill, no_skill)
        for _, with_skill, no_skill in comparisons_for(results)
        if with_skill and no_skill
    ]


def comparisons_for(results):
    comparisons = []
    models = []
    for result in results:
        if result["model"] not in models:
            models.append(result["model"])
    for model in models:
        with_skill = next(
            (result for result in results if result["model"] == model and result["variant"] == "With skill"),
            None,
        )
        no_skill = next(
            (result for result in results if result["model"] == model and result["variant"] == "No skill"),
            None,
        )
        comparisons.append((model, with_skill, no_skill))
    return comparisons


def number(value, kind="number"):
    if value is None:
        return "—"
    if kind == "score":
        return f"{value:.2f}"
    if kind == "cost":
        return f"${value:.4f}".rstrip("0").rstrip(".")
    if kind == "duration":
        return f"{value / 1000:.1f}s"
    if isinstance(value, float) and not value.is_integer():
        return f"{value:.1f}"
    return f"{int(value):,}"


def comparison(with_value, without_value, higher_is_better, positive_word, negative_word):
    if with_value is None or without_value is None:
        return "comparison unavailable"
    if with_value == without_value:
        return "Same"
    if with_value == 0 or without_value == 0:
        return positive_word if (with_value > without_value) == higher_is_better else negative_word
    improved = (with_value > without_value) == higher_is_better
    ratio = (
        with_value / without_value
        if higher_is_better == improved
        else without_value / with_value
    )
    return f"{ratio:.1f}× {positive_word if improved else negative_word}"


def metric_names(results):
    names = []
    for result in results:
        for name in result["metric_scores"]:
            if name not in names:
                names.append(name)
    return names


def paired_medians(pairs, key):
    values = [(result_value(left, key), result_value(right, key)) for left, right in pairs]
    available = [(left, right) for left, right in values if left is not None and right is not None]
    if not available:
        return None, None
    return tuple(statistics.median(side) for side in zip(*available))


def result_value(result, key):
    if key.startswith("metric:"):
        return result["metric_scores"].get(key.removeprefix("metric:"))
    return result.get(key)


def measure_specs(results):
    specs = [
        (f"metric:{name}", name, "score", True, "better", "worse")
        for name in metric_names(results)
    ]
    specs.extend(
        [
            ("input_tokens", "Input tokens", "number", False, "fewer", "more"),
            ("output_tokens", "Output tokens", "number", False, "fewer", "more"),
            ("tokens", "Tokens", "number", False, "fewer", "more"),
            ("cost", "Estimated cost", "cost", False, "lower", "higher"),
            ("duration_ms", "Duration", "duration", False, "faster", "slower"),
            ("turns", "Turns", "number", False, "fewer", "more"),
            ("tool_calls", "Tool calls", "number", False, "fewer", "more"),
        ]
    )
    return specs


def render_overview(suites, all_results):
    specs = measure_specs(all_results)
    headings = "".join(f"<th>{escape(label)}</th>" for _, label, *_ in specs)
    rows = []
    for suite in suites:
        rows.append(
            f'<tr class="suite-row"><td colspan="{len(specs) + 2}"><a class="entity-id" href="#suite-{suite["id"].lower()}" data-view="case">{suite["id"]}</a> · Suite · {escape(suite["name"])}</td></tr>'
        )
        for case in suite["cases"]:
            rows.append(
                f'<tr class="case-row"><td colspan="{len(specs) + 2}"><a class="entity-id" href="#case-{case["id"].lower()}" data-case="{case["id"]}">{case["id"]}</a> · Case · {escape(case["name"])}</td></tr>'
            )
            for model, with_skill, no_skill in comparisons_for(case["results"]):
                if not with_skill or not no_skill:
                    present = with_skill or no_skill
                    missing = "No skill" if with_skill else "With skill"
                    rows.append(
                        f'<tr class="unavailable"><td><a class="entity-id" href="#case-{case["id"].lower()}" data-case="{case["id"]}">{case["id"]}</a> · {escape(model)}<small><a href="#result-{present["id"].lower()}" data-case="{case["id"]}">{present["id"]}</a> {escape(present["variant"].lower())}</small></td><td colspan="{len(specs) + 1}"><strong>comparison unavailable</strong> — missing {missing} result.</td></tr>'
                    )
                    continue
                cells = []
                for key, _, kind, higher, positive, negative in specs:
                    with_value = result_value(with_skill, key)
                    without_value = result_value(no_skill, key)
                    label = comparison(with_value, without_value, higher, positive, negative)
                    css = "improved" if label not in ("Same", "comparison unavailable") and positive in label else "regressed" if negative in label else "unchanged"
                    cells.append(
                        f'<td class="{css}"><strong>{escape(label)}</strong><small>{number(with_value, kind)} / {number(without_value, kind)}</small></td>'
                    )
                rows.append(
                    "<tr><td>"
                    f'<a class="entity-id" href="#case-{case["id"].lower()}" data-case="{case["id"]}">{case["id"]}</a> · {escape(with_skill["model"])}'
                    f'<small><a href="#result-{with_skill["id"].lower()}" data-case="{case["id"]}">{with_skill["id"]}</a> with skill / <a href="#result-{no_skill["id"].lower()}" data-case="{case["id"]}">{no_skill["id"]}</a> no skill</small></td>'
                    f'<td>{"Pass" if with_skill["success"] else "Fail"} / {"Pass" if no_skill["success"] else "Fail"}</td>'
                    + "".join(cells)
                    + "</tr>"
                )
    return f"""
    <section id="overview-view" class="matrix-view">
      <div class="view-head"><div><span class="entity-label">Evaluation run</span><h1>Skill impact overview</h1><p>Each row pairs the same case and model. Raw values show with skill / no skill.</p></div><button class="download-button" type="button">Download JSON</button></div>
      <div class="summary-strip"><span><strong>{sum(len(pairs_for(case['results'])) for suite in suites for case in suite['cases'])}</strong> paired comparisons</span><span><strong>{len(all_results)}</strong> scenario results</span></div>
      <div class="matrix-wrap"><table class="matrix"><thead><tr><th>Model pair</th><th>Overall result</th>{headings}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>
    </section>"""


def cell_class(value, values, higher_is_better):
    available = [item for item in values if item is not None]
    if value is None or len(set(available)) < 2:
        return ""
    best = max(available) if higher_is_better else min(available)
    worst = min(available) if higher_is_better else max(available)
    return "best" if value == best else "worst" if value == worst else ""


def render_all_results(suites, all_results):
    specs = measure_specs(all_results)
    headings = "".join(f"<th>{escape(label)}</th>" for _, label, *_ in specs)
    rows = []
    for suite in suites:
        suite_results = [result for case in suite["cases"] for result in case["results"]]
        rows.append(
            f'<tr class="suite-row"><td colspan="{len(specs) + 4}"><a class="entity-id" href="#suite-{suite["id"].lower()}" data-view="case">{suite["id"]}</a> · Suite · {escape(suite["name"])} <small>{len(suite_results)} results</small></td></tr>'
        )
        for case in suite["cases"]:
            rows.append(
                f'<tr class="case-row"><td colspan="{len(specs) + 4}"><a class="entity-id" href="#case-{case["id"].lower()}" data-case="{case["id"]}">{case["id"]}</a> · Case · {escape(case["name"])} <small>{len(case["results"])} results</small></td></tr>'
            )
            for result in case["results"]:
                cells = []
                for key, _, kind, higher, *_ in specs:
                    value = result_value(result, key)
                    values = [result_value(other, key) for other in case["results"]]
                    cells.append(
                        f'<td class="{cell_class(value, values, higher)}">{number(value, kind)}</td>'
                    )
                status = "Pass" if result["success"] else "Fail"
                rows.append(
                    f'<tr><td><a class="entity-id" href="#result-{result["id"].lower()}" data-case="{case["id"]}">{result["id"]}</a></td><td>{escape(result["model"])}</td><td>{escape(result["variant"])}</td><td class="{status.lower()}-text">{status}</td>{"".join(cells)}</tr>'
                )
    pass_rate = (sum(result["success"] for result in all_results) / len(all_results) * 100) if all_results else 0
    return f"""
    <section id="results-view" class="matrix-view" hidden>
      <div class="view-head"><div><span class="entity-label">Evaluation run</span><h1>All results</h1><p>Suite and case groups with every persisted value.</p></div><button class="download-button" type="button">Download JSON</button></div>
      <div class="summary-strip"><span><strong>{len(all_results)}</strong> scenario results</span><span><strong>{pass_rate:.1f}%</strong> pass rate</span></div>
      <div class="legend"><i class="key best"></i> Best within case <i class="key worst"></i> Worst within case</div>
      <div class="matrix-wrap"><table class="matrix"><thead><tr><th>ID</th><th>Model</th><th>Skill variant</th><th>Result</th>{headings}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>
    </section>"""


def aggregate_rows(case_results):
    pairs = pairs_for(case_results)
    rows = []
    for key, label, kind, higher, positive, negative in measure_specs(case_results):
        with_value, without_value = paired_medians(pairs, key)
        rows.append(
            f"<tr><td>{escape(label)}</td><td>{number(with_value, kind)}</td><td>{number(without_value, kind)}</td><td>{escape(comparison(with_value, without_value, higher, positive, negative))}</td></tr>"
        )
    return "".join(rows)


def aggregate_impact(case_results):
    pairs = pairs_for(case_results)
    if not pairs:
        return '<div class="impact"><strong>comparison unavailable</strong><span>No paired model results</span></div>'
    wanted = [
        spec
        for spec in measure_specs(case_results)
        if spec[0] in ("tokens", "cost", "duration_ms", "tool_calls")
        or spec[1] == "Response quality"
    ]
    cards = []
    for key, label, kind, higher, positive, negative in wanted:
        with_value, without_value = paired_medians(pairs, key)
        cards.append(
            f'<div class="impact"><span>{escape(label)}</span><strong>{escape(comparison(with_value, without_value, higher, positive, negative))}</strong><small>{number(with_value, kind)} / {number(without_value, kind)}</small></div>'
        )
    return "".join(cards)


def render_result(result):
    status = "Pass" if result["success"] else "Fail"
    metric_rows = []
    for metric in result["metrics"]:
        metric_status = "Pass" if metric.get("success") else "Fail"
        metric_rows.append(
            "<tr>"
            f'<td>{escape(metric.get("name", "Unnamed metric"))}</td>'
            f'<td class="{metric_status.lower()}-text">{metric_status}</td>'
            f'<td>{number(metric.get("score"), "score")}</td>'
            f'<td>{number(metric.get("threshold"), "score")}</td>'
            f'<td>{escape(metric.get("reason") or "No reason stored")}</td></tr>'
        )
    tool_sections = []
    for index, tool in enumerate(result["tools"], 1):
        arguments = first(tool, "inputParameters", "input", "arguments", default={})
        output = first(tool, "output", "result", default="Unavailable")
        tool_sections.append(
            f"""<section class="turn tool"><div class="turn-label">Tool call {index}</div><details class="tool-call"><summary>{escape(tool.get('name', 'Unnamed tool'))}</summary><div class="tool-body"><div><strong>Arguments</strong><pre>{escape(pretty(arguments))}</pre></div><div><strong>Output</strong><pre>{escape(pretty(output))}</pre></div></div></details></section>"""
        )
    return f"""
      <details id="result-{result['id'].lower()}" class="result-detail">
        <summary><a class="entity-id" href="#result-{result['id'].lower()}">{result['id']}</a><strong>{escape(result['model'])}</strong><small>{escape(result['variant'])}</small><span class="status {status.lower()}">{status}</span></summary>
        <div class="result-content">
          <div class="facts"><span>{number(result['tokens'])} tokens</span><span>{number(result['cost'], 'cost')} estimated cost</span><span>{number(result['duration_ms'], 'duration')}</span><span>{number(result['turns'])} turns</span><span>{number(result['tool_calls'])} tool calls</span></div>
          <table class="metrics"><thead><tr><th>Metric</th><th>Status</th><th>Score</th><th>Threshold</th><th>Reason</th></tr></thead><tbody>{''.join(metric_rows)}</tbody></table>
          <div class="trace"><section class="turn user"><div class="turn-label">User input</div><div class="message">{escape(result['input'])}</div></section>{''.join(tool_sections)}<section class="turn assistant"><div class="turn-label">Assistant · final response</div><div class="message">{escape(result['output'])}</div></section></div>
        </div>
      </details>"""


def render_case(case, suite):
    results = case["results"]
    pairs = pairs_for(results)
    specs = measure_specs(results)
    model_headings = "".join(f"<th>{escape(label)}</th>" for _, label, *_ in specs)
    model_rows = []
    for model, with_skill, no_skill in comparisons_for(results):
        if not with_skill or not no_skill:
            missing = "No skill" if with_skill else "With skill"
            model_rows.append(
                f'<tr class="unavailable"><td>{escape(model)}</td><td colspan="{len(specs) + 1}"><strong>comparison unavailable</strong> — missing {missing} result.</td></tr>'
            )
            continue
        cells = []
        for key, _, kind, higher, positive, negative in specs:
            with_value = result_value(with_skill, key)
            without_value = result_value(no_skill, key)
            cells.append(
                f'<td><strong>{escape(comparison(with_value, without_value, higher, positive, negative))}</strong><small>{number(with_value, kind)} / {number(without_value, kind)}</small></td>'
            )
        model_rows.append(
            f"<tr><td>{escape(with_skill['model'])}</td><td>{'Pass' if with_skill['success'] else 'Fail'} / {'Pass' if no_skill['success'] else 'Fail'}</td>{''.join(cells)}</tr>"
        )
    comparison_copy = f"{len(pairs)} paired model comparison{'s' if len(pairs) != 1 else ''}" if pairs else "comparison unavailable"
    return f"""
      <article id="case-panel-{case['id'].lower()}" class="case-panel" data-case-panel="{case['id']}" hidden>
        <span class="entity-label"><a class="entity-id" href="#suite-{suite['id'].lower()}">{suite['id']}</a> · Suite</span><p>{escape(suite['name'])}</p>
        <span class="entity-label"><a class="entity-id" href="#case-{case['id'].lower()}">{case['id']}</a> · Case</span><h1>{escape(case['name'])}</h1>
        <section><h2>Case instructions</h2><div class="instructions">{escape(results[0]['input'] if results else 'Unavailable')}</div></section>
        <div class="facts"><span>{escape(comparison_copy)}</span><span>{len(results)} scenario results</span><span>With skill vs No skill</span></div>
        <h2>Aggregate impact</h2><div class="impact-grid">{aggregate_impact(results)}</div>
        <h2>All metric changes</h2><p>Aggregate values pair each model with itself before taking the median.</p><table class="metrics"><thead><tr><th>Metric</th><th>With skill</th><th>No skill</th><th>Change</th></tr></thead><tbody>{aggregate_rows(results)}</tbody></table>
        <h2>Per-model comparisons</h2><p>Raw values show with skill / no skill.</p><div class="matrix-wrap"><table class="metrics"><thead><tr><th>Model</th><th>Overall result</th>{model_headings}</tr></thead><tbody>{''.join(model_rows) or f'<tr><td colspan="{len(specs) + 2}">comparison unavailable</td></tr>'}</tbody></table></div>
        <h2>Scenario results</h2>{''.join(render_result(result) for result in results)}
      </article>"""


def render_case_view(suites):
    navigation = []
    panels = []
    for suite in suites:
        cases = []
        for case in suite["cases"]:
            links = "".join(
                f'<a href="#result-{result["id"].lower()}" data-case="{case["id"]}"><span class="dot {"pass" if result["success"] else "fail"}"></span><strong>{result["id"]}</strong> · {escape(result["model"])} · {escape(result["variant"])}</a>'
                for result in case["results"]
            )
            cases.append(
                f'<details id="case-{case["id"].lower()}" open><summary><button type="button" data-case="{case["id"]}"><span class="entity-id">{case["id"]}</span> · {escape(case["name"])}</button></summary>{links}</details>'
            )
            panels.append(render_case(case, suite))
        navigation.append(
            f'<details id="suite-{suite["id"].lower()}" open><summary><span class="entity-id">{suite["id"]}</span> · {escape(suite["name"])}</summary>{"".join(cases)}</details>'
        )
    return f"""
    <section id="case-view" class="report-grid" hidden>
      <aside aria-label="Case navigation"><h2>Evaluation results</h2>{''.join(navigation)}</aside>
      <main>{''.join(panels)}</main>
    </section>"""


STYLE = """
:root{--ink:#18212b;--muted:#66717d;--rule:#d7dde3;--paper:#fff;--soft:#f4f6f8;--good:#176b45;--bad:#a12b2b;--header:64px;color-scheme:light}
*{box-sizing:border-box}body{margin:0;color:var(--ink);background:var(--paper);font:14px/1.45 ui-sans-serif,system-ui,sans-serif}a{color:inherit}button{font:inherit}.report-header{position:sticky;top:0;z-index:20;background:#17212b;color:#fff;min-height:var(--header);padding:12px 24px;display:flex;align-items:center;justify-content:space-between}.view-tabs{display:flex;gap:5px}.view-tabs button,.download-button{border:1px solid #89929c;border-radius:5px;background:transparent;color:inherit;padding:8px 12px;cursor:pointer}.view-tabs button.active{background:#fff;color:#17212b}.view-tabs button:focus-visible,.download-button:focus-visible,a:focus-visible,summary:focus-visible{outline:3px solid #efb83d;outline-offset:2px}.saved{color:#d7dde3}.matrix-view{padding:28px}.view-head{display:flex;justify-content:space-between;gap:20px;align-items:start}.view-head h1,.case-panel h1{margin:.2rem 0}.matrix-view .download-button{color:var(--ink)}.summary-strip,.facts{display:flex;gap:24px;flex-wrap:wrap;background:var(--soft);padding:12px;margin:18px 0}.summary-strip span,.facts span{white-space:nowrap}.matrix-wrap{overflow:auto;border:1px solid var(--rule)}table{border-collapse:collapse;width:100%}th,td{padding:9px 11px;border-bottom:1px solid var(--rule);vertical-align:top;text-align:left;white-space:nowrap}th{position:sticky;top:var(--header);background:#e9edf1;z-index:3;color:var(--muted)}td small,.matrix td a+small{display:block;color:var(--muted)}.suite-row td{background:#293746;color:#fff;font-weight:700}.case-row td{background:#e9edf1;font-weight:650}.unavailable td{background:#fff8df}.best{background:#def2e7}.worst{background:#f9dddd}.improved,.pass-text{color:var(--good)}.regressed,.fail-text{color:var(--bad)}.entity-id{font-family:ui-monospace,monospace;font-weight:750}.entity-label,.turn-label{color:var(--muted);font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.04em}.legend{margin:10px 0}.key{display:inline-block;width:12px;height:12px;margin:0 4px 0 14px}.report-grid{display:grid;grid-template-columns:280px minmax(0,1fr)}aside{border-right:1px solid var(--rule);padding:24px;min-height:calc(100vh - var(--header));background:var(--soft)}aside details{scroll-margin-top:calc(var(--header) + 14px)}aside summary{padding:6px 0}aside summary button{border:0;background:transparent;text-align:left;cursor:pointer;padding:0}aside a{display:block;padding:5px 0 5px 18px;text-decoration:none}.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}.dot.pass{background:var(--good)}.dot.fail{background:var(--bad)}main{padding:28px;min-width:0}.case-panel,.result-detail{scroll-margin-top:calc(var(--header) + 14px)}.case-panel section{margin:20px 0}.instructions,.message{white-space:pre-wrap;border-left:3px solid #89929c;padding:12px;background:var(--soft)}.metrics{margin:10px 0 24px}.metrics th{top:var(--header)}.matrix-wrap th{top:0}.result-detail{border:1px solid var(--rule);margin:10px 0}.result-detail>summary{display:grid;grid-template-columns:60px 1fr 1fr auto;gap:12px;align-items:center;padding:12px;cursor:pointer}.result-content{padding:0 14px 14px}.turn{margin:12px 0}.tool-call{border:1px solid #c7b8db}.tool-call summary{padding:9px;background:#eee8f5;font-weight:700}.tool-body{display:grid;grid-template-columns:1fr 1fr}.tool-body>div{padding:10px;min-width:0}.tool-body>div+div{border-left:1px solid #c7b8db}pre{overflow:auto;white-space:pre-wrap;margin:.5rem 0 0}.privacy{padding:20px 28px;color:var(--muted);border-top:1px solid var(--rule)}[hidden]{display:none!important}
.impact-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));border:1px solid var(--rule);margin:10px 0 24px}.impact{padding:12px}.impact+.impact{border-left:1px solid var(--rule)}.impact span,.impact strong{display:block}
@media(max-width:800px){:root{--header:100px}.report-header,.view-head{align-items:start;flex-direction:column}.report-grid{display:block}aside{min-height:0;border-right:0;border-bottom:1px solid var(--rule)}.tool-body{grid-template-columns:1fr}.tool-body>div+div{border-left:0;border-top:1px solid #c7b8db}}
"""


SCRIPT = """
const views = ['overview', 'results', 'case'];
function setView(view) {
  for (const name of views) {
    document.getElementById(name + '-view').hidden = name !== view;
    document.getElementById(name + '-tab').classList.toggle('active', name === view);
  }
}
function showCase(id) {
  setView('case');
  for (const panel of document.querySelectorAll('[data-case-panel]')) panel.hidden = panel.dataset.casePanel !== id;
}
function followFragment() {
  const target = document.getElementById(location.hash.slice(1));
  if (!target) return;
  const panel = target.closest('[data-case-panel]');
  const caseId = panel?.dataset.casePanel || target.querySelector('[data-case]')?.dataset.case;
  if (!caseId) return;
  showCase(caseId);
  if (target.tagName === 'DETAILS') target.open = true;
  target.scrollIntoView();
}
for (const name of views) document.getElementById(name + '-tab').addEventListener('click', () => setView(name));
for (const link of document.querySelectorAll('[data-case]')) link.addEventListener('click', () => showCase(link.dataset.case));
for (const link of document.querySelectorAll('[data-view="case"]')) link.addEventListener('click', () => setView('case'));
for (const button of document.querySelectorAll('.download-button')) button.addEventListener('click', () => {
  const text = document.getElementById('source-data').textContent;
  const url = URL.createObjectURL(new Blob([text], {type: 'application/json'}));
  const link = Object.assign(document.createElement('a'), {href: url, download: 'mcp-eval-results.json'});
  link.click();
  URL.revokeObjectURL(url);
});
const firstPanel = document.querySelector('[data-case-panel]');
if (firstPanel) firstPanel.hidden = false;
window.addEventListener('hashchange', followFragment);
followFragment();
"""


def render(source, source_path):
    _, results, suites = normalize(source)
    saved = datetime.datetime.fromtimestamp(source_path.stat().st_mtime).astimezone()
    saved_iso = saved.isoformat(timespec="seconds")
    saved_text = saved.strftime("%d %b %Y, %H:%M:%S %Z")
    source_json = json.dumps(source, indent=2, ensure_ascii=False)
    source_json = source_json.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'"><title>MCP evaluation report</title><style>{STYLE}</style></head>
<body><header class="report-header"><strong>MCP evaluation report</strong><span class="saved">Results saved <time datetime="{saved_iso}">{escape(saved_text)}</time></span><nav class="view-tabs" aria-label="Report views"><button id="overview-tab" class="active" type="button">Overview</button><button id="results-tab" type="button">All results</button><button id="case-tab" type="button">Case detail</button></nav></header>
{render_overview(suites, results)}{render_all_results(suites, results)}{render_case_view(suites)}
<p class="privacy">This report contains local evaluation inputs, tool outputs, and judge reasons. Keep it private and do not upload it.</p>
<script type="application/json" id="source-data">{source_json}</script><script>{SCRIPT}</script></body></html>"""


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate a private local DeepEval HTML report")
    parser.add_argument("input", nargs="?", default=DEFAULT_INPUT)
    parser.add_argument("-o", "--output", default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    source_path = pathlib.Path(args.input)
    output_path = pathlib.Path(args.output)
    source = json.loads(source_path.read_text())
    page = render(source, source_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        os.fchmod(output.fileno(), 0o600)
        output.write(page)
    print(output_path)


if __name__ == "__main__":
    main()
