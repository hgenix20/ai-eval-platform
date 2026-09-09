"""Render a GateReport as JUnit XML, for CI systems that display test results
from a JUnit file (e.g. a GitHub Actions test-reporter step)."""

from __future__ import annotations

# Suppressed below: bandit's xml.sax blacklist targets parsing untrusted XML
# input. This module only calls escape() to produce text, and never parses XML.
from xml.sax.saxutils import escape  # nosec B406

from .compare import GateReport


def to_junit(report: GateReport) -> str:
    """Render `report` as a single JUnit <testsuite> with one <testcase> per
    verdict. A fail or unstable verdict becomes a <failure> child; a
    not_measured verdict becomes a <skipped> child; a pass verdict is a bare
    testcase. Text is XML-escaped via xml.sax.saxutils.escape, which only
    substitutes the required entities and does not evaluate or parse markup.
    """
    failures = sum(v.verdict in ("fail", "unstable") for v in report.verdicts)
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<testsuite name="evalplat-gate" tests="{len(report.verdicts)}" failures="{failures}">',
    ]
    for v in report.verdicts:
        name = escape(f"{v.suite}.{v.metric}")
        detail = escape(v.detail)
        if v.verdict in ("fail", "unstable"):
            lines.append(f'  <testcase name="{name}"><failure message="{detail}"/></testcase>')
        elif v.verdict == "not_measured":
            lines.append(f'  <testcase name="{name}"><skipped message="{detail}"/></testcase>')
        else:
            lines.append(f'  <testcase name="{name}"/>')
    lines.append("</testsuite>")
    return "\n".join(lines) + "\n"
