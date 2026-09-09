from pathlib import Path

import pytest

from eval_platform.budget import Budget
from eval_platform.suites import CaseError, load_cases, run_suite
from eval_platform.targets import ScriptedTarget
from eval_platform.types import Case, Expect

CASE = """
name: scripted-ok
goal: g
target_requirements: [scripted]
script:
  - {kind: tool, name: lookup, output: v, cost_usd: 0.01, latency_ms: 3}
  - {kind: model, name: final, status: completed, answer: done}
expect: {status: completed, tools_used: {strict: [lookup]}}
"""


def test_load_cases_parses_and_names_bad_file(tmp_path: Path):
    (tmp_path / "a.yaml").write_text(CASE, encoding="utf-8")
    assert load_cases(tmp_path)[0].name == "scripted-ok"
    (tmp_path / "b.yaml").write_text("name: x\n", encoding="utf-8")
    with pytest.raises(CaseError, match=r"b\.yaml"):
        load_cases(tmp_path)


def test_run_suite_passes_skips_and_fails(tmp_path: Path):
    (tmp_path / "a.yaml").write_text(CASE, encoding="utf-8")
    cases = [
        *load_cases(tmp_path),
        Case(name="needs-memory", goal="g", target_requirements=["memory"], expect=Expect()),
        Case(name="no-script", goal="g", target_requirements=["scripted"], expect=Expect()),
    ]
    result = run_suite(
        "offline_core", cases, ScriptedTarget(), budget=Budget(max_usd=1, max_wall_s=60)
    )
    by = {c.name: c for c in result.cases}
    assert by["scripted-ok"].passed
    assert by["needs-memory"].skipped_reason and by["needs-memory"].trajectory is None
    assert not by["no-script"].passed and by["no-script"].grades[0].dimension == "run"
    assert result.metrics["cases_total"] == 3 and result.metrics["cases_skipped"] == 1
    assert result.metrics["pass_rate"] == 0.5


def test_run_suite_stops_on_budget(tmp_path: Path):
    """Each case costs $0.01 against a $0.015 ceiling, so the second one's
    charge trips it. That case ran and was graded before the charge, so its
    result is kept in full; only the cases after it are skipped."""
    for i in range(3):
        (tmp_path / f"{i}.yaml").write_text(CASE.replace("scripted-ok", f"c{i}"), encoding="utf-8")
    result = run_suite(
        "s", load_cases(tmp_path), ScriptedTarget(), budget=Budget(max_usd=0.015, max_wall_s=60)
    )
    assert result.meta["budget_exceeded"] is True
    assert result.metrics["cases_total"] == 3
    by = {c.name: c for c in result.cases}

    assert by["c0"].passed and by["c0"].trajectory is not None

    tripping = by["c1"]
    assert tripping.trajectory is not None, "the case that trips the budget keeps its trajectory"
    assert tripping.passed and tripping.skipped_reason is None
    assert tripping.trajectory.tools_used() == ["lookup"]

    assert by["c2"].trajectory is None and by["c2"].skipped_reason == "budget exceeded"
    assert result.metrics["cases_skipped"] == 1
    assert result.meta["spent_usd"] == pytest.approx(0.02)
