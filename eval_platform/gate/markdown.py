"""Render a GateReport as a markdown table, for posting into a PR comment or
a build summary."""

from __future__ import annotations

from .compare import GateReport


def _fmt(x: float | None) -> str:
    """Render a metric value for display, or "n/a" when it was not measured."""
    return "n/a" if x is None else f"{x:.4f}"


def to_markdown(report: GateReport) -> str:
    """Render `report` as a markdown heading (PASS or FAIL) followed by a
    table with one row per verdict: suite, metric, baseline, current,
    threshold, verdict, detail."""
    head = "PASS" if report.passed else "FAIL"
    rows = [
        f"## Eval gate: {head}",
        "",
        "| suite | metric | baseline | current | threshold | verdict | detail |",
        "|---|---|---|---|---|---|---|",
    ]
    for v in report.verdicts:
        cells = [
            v.suite,
            v.metric,
            _fmt(v.baseline),
            _fmt(v.current),
            v.threshold,
            v.verdict,
            v.detail,
        ]
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows) + "\n"
