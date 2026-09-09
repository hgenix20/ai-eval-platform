from pathlib import Path

import pytest

pytest.importorskip("agent_platform")

from eval_platform.budget import Budget
from eval_platform.suites import load_cases, run_suite
from eval_platform.targets import AgentPlatformLocalTarget

SUITE = Path(__file__).resolve().parents[1] / "suites" / "offline_core"
pytestmark = pytest.mark.agent_platform


def test_offline_core_has_twelve_cases_and_all_pass():
    cases = load_cases(SUITE)
    assert len(cases) == 12
    result = run_suite(
        "offline_core",
        cases,
        AgentPlatformLocalTarget(),
        budget=Budget(max_usd=0.0, max_wall_s=120),
    )
    failed = [
        (c.name, [g.explanation for g in c.grades if not g.passed])
        for c in result.cases
        if not c.passed
    ]
    assert failed == []
    assert result.metrics["pass_rate"] == 1.0 and result.metrics["cases_skipped"] == 0
