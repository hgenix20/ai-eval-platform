import pytest

pytest.importorskip("agent_platform")

from agent_platform.demo import build_app
from fastapi.testclient import TestClient

from eval_platform.targets import (
    AgentPlatformHttpTarget,
    AgentPlatformLocalTarget,
    TargetUnavailable,
)
from eval_platform.types import Case, Expect

pytestmark = pytest.mark.agent_platform


def test_local_target_holds_the_approval_gate():
    case = Case(
        name="gate",
        goal="email the team",
        expect=Expect(),
        planner=['{"action": "tool", "tool": "send_email", "arguments": {"to": "a@b"}}'],
    )
    t = AgentPlatformLocalTarget().run(case)
    assert t.status == "waiting_approval" and t.side_effects == ()


def test_local_target_records_tool_then_answer():
    case = Case(
        name="t",
        goal="find revenue",
        expect=Expect(),
        planner=[
            '{"action": "tool", "tool": "lookup", "arguments": {"key": "revenue"}}',
            '{"action": "final", "answer": "revenue is value-for-revenue"}',
        ],
        validator=['{"approved": true, "reason": "ok"}'],
    )
    t = AgentPlatformLocalTarget().run(case)
    assert t.status == "completed" and t.tools_used() == ["lookup"] and t.wall_ms >= 0


def test_http_target_runs_against_the_demo_app():
    client = TestClient(build_app())
    target = AgentPlatformHttpTarget.from_client(client)
    t = target.run(Case(name="h", goal="say hi", expect=Expect()))
    assert t.status in {"completed", "failed", "waiting_approval"} and t.meta["run_id"]


def test_http_target_reports_unavailable_when_server_is_down():
    with pytest.raises(TargetUnavailable):
        AgentPlatformHttpTarget("http://127.0.0.1:9", timeout_s=0.5)
