from pathlib import Path

import pytest

pytest.importorskip("agent_platform")

from eval_platform.budget import Budget
from eval_platform.suites import load_cases, run_suite
from eval_platform.targets import AgentPlatformLocalTarget
from eval_platform.types import Case, Expect, Session

SUITE = Path(__file__).resolve().parents[1] / "suites" / "memory"
pytestmark = pytest.mark.agent_platform

OK = '{"approved": true, "reason": "ok"}'


def test_sessions_share_one_memory_store():
    case = Case(
        name="s",
        goal="ignored",
        target_requirements=["agent", "memory"],
        expect=Expect(),
        sessions=[
            Session(
                goal="remember the code word",
                planner=[
                    '{"action": "tool", "tool": "remember", '
                    '"arguments": {"text": "the code word is heron"}}',
                    '{"action": "final", "answer": "stored"}',
                ],
                validator=[OK],
            ),
            Session(
                goal="what is the code word",
                planner=[
                    '{"action": "tool", "tool": "recall", "arguments": {"query": "code word"}}',
                    '{"action": "final", "answer": "heron"}',
                ],
                validator=[OK],
            ),
        ],
    )
    t = AgentPlatformLocalTarget().run(case)
    assert len(t.meta["sessions"]) == 2 and t.answer == "heron"
    recall = [s for s in t.steps if s.kind == "tool" and s.name == "recall"]
    assert recall and "heron" in str(recall[0].output)


def test_memory_suite_runs_all_cases():
    cases = load_cases(SUITE)
    assert len(cases) >= 10
    result = run_suite("memory", cases, AgentPlatformLocalTarget(), budget=Budget(0.0, 600))
    assert result.metrics["cases_skipped"] == 0
    for c in result.cases:
        assert c.trajectory is not None
