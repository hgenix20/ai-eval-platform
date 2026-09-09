"""One self-contained HTML page from suite summaries. No JavaScript, no
external assets, so it can be committed, attached to a CI run, or served
from GitHub Pages unchanged."""

from __future__ import annotations

from collections.abc import Sequence
from html import escape
from typing import Any

_CSS = """
body{font-family:system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#222}
table{border-collapse:collapse;margin:0.5rem 0 1.5rem}
td,th{border:1px solid #ccc;padding:0.3rem 0.6rem;text-align:left}
th{background:#f3f3f3}.fail{color:#a00}.pass{color:#070}pre{background:#f7f7f7;padding:0.8rem;overflow-x:auto}
"""


def _x(m: dict[str, Any]) -> float:
    """Pick the cost metric for the scatter x axis: `usd` for public suites,
    `usd_per_run_p50` for offline suites. Returns 0.0 when neither is present
    or the value is falsy, so a summary missing both never raises."""
    return float(m.get("usd", m.get("usd_per_run_p50", 0.0)) or 0.0)


def _y(m: dict[str, Any]) -> float:
    """Pick the quality metric for the scatter y axis: `accuracy` for public
    suites, `pass_rate` for offline suites. Returns 0.0 when neither is
    present or the value is falsy, so a summary missing both never raises."""
    return float(m.get("accuracy", m.get("pass_rate", 0.0)) or 0.0)


def _scatter(summaries: Sequence[dict[str, Any]]) -> str:
    """Render an inline SVG scatter of cost (x) against quality (y), one
    circle per summary. `summaries` must be non-empty; `render_html` only
    calls this from its non-empty branch, so there is no empty-list case to
    guard here.

    Cost is clamped to >= 0.0 and quality is clamped to [0.0, 1.0] before
    plotting: a metric outside those bounds (for example an accuracy of
    87.0 recorded as a percentage instead of a fraction) would otherwise
    place its point off the canvas with no indication of the problem. A
    clamped point gets " (clamped)" appended to its label so the mistake is
    visible in the rendered page instead of just being invisible off-canvas.

    Scales x by the largest clamped cost seen, falling back to 1.0 when
    every cost is 0, so a single point still lands on the axis instead of
    dividing by zero.
    """
    w, h, pad = 520, 300, 40
    xs = [max(_x(s["metrics"]), 0.0) for s in summaries]
    xmax = max(xs) or 1.0
    pts = []
    for s in summaries:
        raw_x, raw_y = _x(s["metrics"]), _y(s["metrics"])
        x, y = max(raw_x, 0.0), min(max(raw_y, 0.0), 1.0)
        clamped = x != raw_x or y != raw_y
        px = pad + (x / xmax) * (w - 2 * pad)
        py = h - pad - y * (h - 2 * pad)
        text = f"{s['suite']} / {s['target']}" + (" (clamped)" if clamped else "")
        label = escape(text)
        pts.append(
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="5" fill="#2a6"><title>{label}</title></circle>'
            f'<text x="{px + 8:.1f}" y="{py + 4:.1f}" font-size="11">{label}</text>'
        )
    axes = (
        f'<line x1="{pad}" y1="{h - pad}" x2="{w - pad}" y2="{h - pad}" stroke="#888"/>'
        f'<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{h - pad}" stroke="#888"/>'
        f'<text x="{w / 2:.0f}" y="{h - 8}" font-size="11" text-anchor="middle">cost (USD)</text>'
        f'<text x="12" y="{h / 2:.0f}" font-size="11" transform="rotate(-90 12 {h / 2:.0f})" '
        f'text-anchor="middle">accuracy / pass rate</text>'
    )
    return (
        f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img">{axes}{"".join(pts)}</svg>'
    )


def _metrics_table(m: dict[str, Any]) -> str:
    """Render a summary's `metrics` dict as a two-column HTML table. Metric
    names are escaped. A value that converts to float is formatted to 4
    decimal places; a value that does not (for example `None`, which raises
    TypeError, or a non-numeric string, which raises ValueError) is
    rendered instead as its escaped `repr` with a "not numeric" note, so one
    malformed metric does not crash the whole report."""
    cells = []
    for k, v in m.items():
        try:
            value_cell = f"{float(v):.4f}"
        except (TypeError, ValueError):
            value_cell = f"{escape(repr(v))} (not numeric)"
        cells.append(f"<tr><td>{escape(k)}</td><td>{value_cell}</td></tr>")
    return f"<table><tr><th>metric</th><th>value</th></tr>{''.join(cells)}</table>"


def _cases_table(cases: Sequence[dict[str, Any]]) -> str:
    """Render one row per case: name, pass/skip/fail result, and the failed
    grade dimensions joined into one cell. Returns an empty string for an
    empty case list rather than an empty table, so callers can drop it in
    without leaving a header-only table behind."""
    rows = []
    for c in cases:
        if c.get("skipped_reason"):
            rows.append(
                f"<tr><td>{escape(c['name'])}</td><td>skipped</td><td>{escape(c['skipped_reason'])}</td></tr>"
            )
            continue
        failed = "; ".join(
            f"{g['dimension']}: {g['explanation']}"
            for g in c.get("grades", [])
            if not g.get("passed")
        )
        cls = "pass" if c.get("passed") else "fail"
        rows.append(
            f"<tr><td>{escape(c['name'])}</td>"
            f"<td class='{cls}'>{cls}</td><td>{escape(failed)}</td></tr>"
        )
    header = "<tr><th>case</th><th>result</th><th>failed dimensions</th></tr>"
    return f"<table>{header}{''.join(rows)}</table>" if rows else ""


def render_html(
    summaries: Sequence[dict[str, Any]],
    *,
    gate_markdown: str | None = None,
    ledger_total_usd: float | None = None,
) -> str:
    """Render one self-contained HTML report from a list of suite summary
    dicts (the shape written by `SuiteResult.to_dict()`): a header, a
    cost-against-quality scatter, one metrics table and one case table per
    summary, and the gate markdown as preformatted text when given.

    Every summary-supplied string (suite, target, timestamps, case names,
    skip reasons, grade dimensions and explanations) is HTML-escaped before
    it goes into the page, since these values can come from an untrusted
    target's output. The page has no external assets and no JavaScript, so
    it renders the same when opened from disk, attached to a CI run, or
    served as a static page.

    An empty `summaries` list is not an error: the report renders with a
    "No results." notice and no scatter or tables. Missing metrics fall
    back to 0.0 for the scatter (see `_x`/`_y`); a metric value that cannot
    convert to float is rendered as "not numeric" instead of raising (see
    `_metrics_table`), so one malformed summary does not take down the
    whole report. A scatter point whose cost or quality metric falls
    outside its expected range is clamped onto the canvas and labeled
    "(clamped)" (see `_scatter`).
    """
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'><title>Eval report</title>"
        f"<style>{_CSS}</style></head><body>",
        "<h1>Eval report</h1>",
    ]
    if ledger_total_usd is not None:
        parts.append(f"<p>Program spend to date: ${ledger_total_usd:.2f}</p>")
    if not summaries:
        parts.append("<p>No results.</p>")
    else:
        parts.append("<h2>Cost against quality</h2>" + _scatter(summaries))
        for s in summaries:
            parts.append(
                f"<h2>{escape(s['suite'])} on {escape(s['target'])}</h2>"
                f"<p>{escape(s['started_at'])} to {escape(s['finished_at'])}</p>"
                + _metrics_table(s["metrics"])
                + _cases_table(s.get("cases", []))
            )
    if gate_markdown:
        parts.append("<h2>Gate</h2><pre>" + escape(gate_markdown) + "</pre>")
    parts.append("</body></html>")
    return "".join(parts)
