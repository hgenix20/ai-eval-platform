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
