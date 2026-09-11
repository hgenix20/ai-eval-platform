from pathlib import Path

import pytest

pytest.importorskip("agent_platform")

from eval_platform.budget import Budget
from eval_platform.suites import load_cases, run_suite
from eval_platform.targets import AgentPlatformLocalTarget
from eval_platform.targets.convert import run_dict_to_trajectory
from eval_platform.types import Case, Expect

SUITE = Path(__file__).resolve().parents[1] / "suites" / "trajectory"
pytestmark = pytest.mark.agent_platform


def test_converter_fills_tool_inputs_from_recorded_calls():
    run = {
        "outcome": {"status": "completed", "answer": "a"},
        "steps_used": 2,
        "history": [
            {"type": "tool_result", "tool": "lookup", "output": "v"},
            {"type": "proposed_answer", "answer": "a"},
        ],
    }
    t = run_dict_to_trajectory(
        run,
        target="t",
        goal="g",
        wall_ms=1,
        cost_usd=0,
        tool_calls=[{"tool": "lookup", "arguments": {"key": "x"}}],
    )
    assert t.steps[0].input == {"key": "x"}


def test_local_target_records_tool_arguments():
    case = Case(
        name="args",
        goal="g",
        expect=Expect(),
        planner=[
            '{"action": "tool", "tool": "lookup", "arguments": {"key": "revenue"}}',
            '{"action": "final", "answer": "done"}',
        ],
        validator=['{"approved": true, "reason": "ok"}'],
    )
    t = AgentPlatformLocalTarget().run(case)
    assert t.steps[0].kind == "tool" and t.steps[0].input == {"key": "revenue"}


def test_trajectory_suite_has_ten_cases_and_all_pass():
    cases = load_cases(SUITE)
    assert len(cases) >= 10
    result = run_suite("trajectory", cases, AgentPlatformLocalTarget(), budget=Budget(0.0, 300))
    failed = [
        (c.name, [g.explanation for g in c.grades if not g.passed])
        for c in result.cases
        if not c.passed
    ]
    assert failed == []
    assert result.metrics["cases_skipped"] == 0 and "step_efficiency_mean" in result.metrics
