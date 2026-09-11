import re

from eval_platform.reports import render_html


def _summary(suite, target, **metrics):
    return {
        "suite": suite,
        "target": target,
        "started_at": "2026-09-08T10:00:00Z",
        "finished_at": "2026-09-08T10:00:01Z",
        "metrics": metrics,
        "meta": {},
        "cases": [
            {"name": "a", "passed": True, "grades": [], "skipped_reason": None},
            {
                "name": "b",
                "passed": False,
                "grades": [
                    {
                        "dimension": "status",
                        "passed": False,
                        "value": 0,
                        "explanation": "expected x",
                    }
                ],
                "skipped_reason": None,
            },
        ],
    }


def test_render_contains_suites_cases_and_scatter():
    html = render_html(
        [
            _summary("offline_core", "scripted", pass_rate=0.5, usd_per_run_p50=0.0),
            _summary("public_ifeval", "anthropic/x", accuracy=0.8, usd=0.42),
        ],
        gate_markdown="## Eval gate: PASS",
        ledger_total_usd=0.42,
    )
    assert "<html" in html and "offline_core" in html and "public_ifeval" in html
    assert "<svg" in html and html.count("<circle") == 2
    assert "expected x" in html and "Eval gate: PASS" in html and "0.42" in html
    assert "http" not in html.split("<body")[1]  # self-contained: no external assets in the body


def test_render_with_no_summaries_is_valid():
    html = render_html([])
    assert "<html" in html and "No results" in html


def test_scatter_clamps_out_of_range_accuracy():
    # accuracy=87.0 is a percentage recorded by mistake where a 0-1 fraction
    # is expected; it must clamp to the same y as accuracy=1.0, not plot
    # off-canvas, and its label must say so.
    html_mistake = render_html([_summary("public_x", "target", accuracy=87.0, usd=0.1)])
    html_correct = render_html([_summary("public_x", "target", accuracy=1.0, usd=0.1)])
    cy_mistake = re.search(r'cy="([\d.]+)"', html_mistake)
    cy_correct = re.search(r'cy="([\d.]+)"', html_correct)
    assert cy_mistake is not None and cy_correct is not None
    assert cy_mistake.group(1) == cy_correct.group(1)
    assert "(clamped)" in html_mistake
    assert "(clamped)" not in html_correct


def test_render_escapes_hostile_strings():
    payload = "<script>alert(1)</script>"
    summary = {
        "suite": payload,
        "target": payload,
        "started_at": "2026-09-08T10:00:00Z",
        "finished_at": "2026-09-08T10:00:01Z",
        "metrics": {"pass_rate": 0.5},
        "meta": {},
        "cases": [
            {
                "name": payload,
                "passed": False,
                "grades": [{"dimension": "d", "passed": False, "value": 0, "explanation": payload}],
                "skipped_reason": None,
            },
            {"name": "other", "passed": False, "grades": [], "skipped_reason": payload},
        ],
    }
    html = render_html([summary], gate_markdown=payload)
    assert "<script>" not in html
    assert html.count("&lt;script&gt;") >= 6


def test_metrics_table_renders_non_numeric_value_without_crashing():
    html = render_html([_summary("offline_core", "scripted", pass_rate=None)])
    assert "not numeric" in html


def _calibration(judge="faithfulness@1:hf/Qwen/Qwen2.5-3B-Instruct", **over):
    d = {
        "started_at": "2026-09-11T15:18:41+00:00",
        "finished_at": "2026-09-11T15:41:19+00:00",
        "items": 120,
        "judges": [
            {
                "judge": judge,
                "version": "aa8e725",
                "items": 120,
                "unknown": 2,
                "kappa": 0.0763,
                "accuracy": 0.5339,
                "tp": 16,
                "fp": 11,
                "tn": 47,
                "fn": 44,
            }
        ],
        "swap_agreement": 0.7458,
        "swap_pair": [judge, "faithfulness@1:hf/Qwen/Qwen2.5-1.5B-Instruct"],
        "kappa_floor": 0.7,
        "min_swap_agreement": 0.9,
        "calibrated": {judge: [False, "kappa 0.08 < 0.70"]},
    }
    d.update(over)
    return d


def test_calibration_table_appears_only_when_a_report_is_passed():
    summaries = [_summary("groundedness", "mcp:edgar-fixture", pass_rate=0.38)]
    with_table = render_html(summaries, calibration=_calibration())
    without = render_html(summaries)
    assert "Judge calibration" in with_table
    assert "Judge calibration" not in without
    assert "0.0763" in with_table and "kappa 0.08 &lt; 0.70" in with_table
    assert "no" in with_table and "swap agreement" in with_table.lower()
    assert "0.7458" in with_table and "120" in with_table


def test_calibration_table_says_yes_for_a_calibrated_judge():
    cal = _calibration()
    cal["calibrated"] = {cal["judges"][0]["judge"]: [True, "kappa 0.80 >= 0.70"]}
    html = render_html([], calibration=cal)
    assert "yes" in html and "kappa 0.80 &gt;= 0.70" in html


def test_calibration_table_without_a_swap_pair_omits_the_swap_line():
    html = render_html([], calibration=_calibration(swap_agreement=None, swap_pair=None))
    assert "Judge calibration" in html and "swap agreement" not in html


def test_calibration_table_escapes_hostile_strings():
    payload = "<script>alert(1)</script>"
    html = render_html([], calibration=_calibration(judge=payload))
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_calibration_table_survives_a_judge_with_no_verdict():
    cal = _calibration()
    cal["calibrated"] = {}
    html = render_html([], calibration=cal)
    assert "Judge calibration" in html and "no verdict recorded" in html
