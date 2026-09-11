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
    # every case either passed or failed on the recovered dimension with a written reason
    for c in result.cases:
        assert c.trajectory is not None or c.grades
