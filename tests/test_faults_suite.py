from pathlib import Path

import pytest

pytest.importorskip("agent_platform")

from eval_platform.budget import Budget
from eval_platform.suites import load_cases, run_suite
from eval_platform.targets import AgentPlatformLocalTarget

SUITE = Path(__file__).resolve().parents[1] / "suites" / "faults"
pytestmark = pytest.mark.agent_platform


def test_faults_suite_runs_every_case_and_reports_recovery_rate():
    cases = load_cases(SUITE)
    assert len(cases) >= 10
    result = run_suite("faults", cases, AgentPlatformLocalTarget(), budget=Budget(0.0, 600))
    assert result.metrics["cases_skipped"] == 0
    assert 0.0 <= result.metrics["recovery_rate"] <= 1.0
    assert 0.0 <= result.metrics["expectation_match_rate"] <= 1.0
    # every case either passed or failed on the recovered dimension with a written reason
    for c in result.cases:
        assert c.trajectory is not None or c.grades


def test_recovery_rate_counts_only_the_cases_that_were_meant_to_recover():
    """The measured split, and why the two metrics differ: eight of the
    eleven cases expect recovery and six of those recover, while nine of all
    eleven end the way their case predicted."""
    cases = load_cases(SUITE)
    result = run_suite("faults", cases, AgentPlatformLocalTarget(), budget=Budget(0.0, 600))
    expecting = [
        c
        for c in result.cases
        if any(g.dimension == "recovery_expected" and g.value == 1.0 for g in c.grades)
    ]
    recovered = [
        c for c in expecting if any(g.dimension == "recovered" and g.value == 1.0 for g in c.grades)
    ]
    carrying = [c for c in result.cases if any(g.dimension == "recovered" for g in c.grades)]
    matched = [
        c for c in carrying if any(g.dimension == "recovered" and g.passed for g in c.grades)
    ]
    assert (len(recovered), len(expecting)) == (6, 8)
    assert (len(matched), len(carrying)) == (9, 11)
    assert result.metrics["recovery_rate"] == pytest.approx(0.75)
    assert result.metrics["expectation_match_rate"] == pytest.approx(9 / 11)
