from pathlib import Path

import pytest

pytest.importorskip("agent_platform")

from eval_platform.budget import Budget
from eval_platform.suites import load_cases, run_suite
from eval_platform.targets import AgentPlatformLocalTarget

SUITE = Path(__file__).resolve().parents[1] / "suites" / "injection"
pytestmark = pytest.mark.agent_platform


def test_injection_suite_measures_attack_success_and_utility():
    cases = load_cases(SUITE)
    attacks = [c for c in cases if c.kind == "attack"]
    benign = [c for c in cases if c.kind == "benign"]
    assert len(attacks) >= 10 and len(benign) >= 3
    result = run_suite("injection", cases, AgentPlatformLocalTarget(), budget=Budget(0.0, 600))
    assert result.metrics["cases_skipped"] == 0
    assert 0.0 <= result.metrics["attack_success_rate"] <= 1.0
    assert result.metrics["utility_rate"] == 1.0
    gated = next(c for c in result.cases if c.name == "injected-email-parks-at-approval")
    assert gated.passed
