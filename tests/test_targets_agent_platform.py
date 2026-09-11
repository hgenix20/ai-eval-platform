from typing import Any

import pytest

pytest.importorskip("agent_platform")

import httpx
from agent_platform.demo import build_app
from agent_platform.service import create_app
from fastapi.testclient import TestClient

from eval_platform.targets import (
    AgentPlatformHttpTarget,
    AgentPlatformLocalTarget,
    ScriptedTarget,
    TargetUnavailable,
)
from eval_platform.targets.agent_platform_local import build_world
from eval_platform.types import Case, Expect

pytestmark = pytest.mark.agent_platform


class _StubResponse:
    """A minimal stand-in for an httpx/TestClient response: just enough of
    the surface `AgentPlatformHttpTarget` actually uses (`status_code`,
    `json()`, `text`, `raise_for_status()`) to drive it from a plain stub
    client instead of a real HTTP server."""

    def __init__(self, status_code: int = 200, json_data: Any = None, text: str = "") -> None:
        self.status_code = status_code
        self._json = {} if json_data is None else json_data
        self.text = text

    def json(self) -> Any:
        return self._json

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "http://stub")
            response = httpx.Response(self.status_code, request=request, text=self.text)
            raise httpx.HTTPStatusError(
                f"status {self.status_code}", request=request, response=response
            )


class _FailingRunsClient:
    """Stub client whose `POST /runs` answers with an HTTP 422."""

    def get(self, url: str, **kw: Any) -> _StubResponse:
        if url == "/costs":
            return _StubResponse(json_data={"total_usd": 0.0})
        raise AssertionError(f"unexpected GET {url}")

    def post(self, url: str, **kw: Any) -> _StubResponse:
        if url == "/runs":
            return _StubResponse(status_code=422, json_data={"detail": "bad goal"}, text="bad goal")
        raise AssertionError(f"unexpected POST {url}")


class _FailingCostsClient:
    """Stub client whose `/costs` answers with an HTTP 500 on every call,
    while `/runs` succeeds normally."""

    def get(self, url: str, **kw: Any) -> _StubResponse:
        if url == "/costs":
            return _StubResponse(
                status_code=500, json_data={"detail": "meter down"}, text="meter down"
            )
        raise AssertionError(f"unexpected GET {url}")

    def post(self, url: str, **kw: Any) -> _StubResponse:
        if url == "/runs":
            return _StubResponse(
                json_data={
                    "run_id": "r2",
                    "goal": "x",
                    "status": "completed",
                    "outcome": {"status": "completed", "answer": "ok"},
                    "history": [],
                    "steps_used": 0,
                }
            )
        raise AssertionError(f"unexpected POST {url}")


class _CostTrackingClient:
    """Stub client whose `/costs` reports 0.10 before the run and 0.35
    after, so the target's cost accounting can be checked as a delta."""

    def __init__(self) -> None:
        self._costs = iter([0.10, 0.35])

    def get(self, url: str, **kw: Any) -> _StubResponse:
        if url == "/costs":
            return _StubResponse(json_data={"total_usd": next(self._costs)})
        raise AssertionError(f"unexpected GET {url}")

    def post(self, url: str, **kw: Any) -> _StubResponse:
        if url == "/runs":
            return _StubResponse(
                json_data={
                    "run_id": "r1",
                    "goal": "x",
                    "status": "completed",
                    "outcome": {"status": "completed", "answer": "ok"},
                    "history": [],
                    "steps_used": 0,
                }
            )
        raise AssertionError(f"unexpected POST {url}")


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


def test_http_target_wraps_http_status_error_as_value_error():
    target = AgentPlatformHttpTarget.from_client(_FailingRunsClient())
    with pytest.raises(ValueError, match="422"):
        target.run(Case(name="bad", goal="x", expect=Expect()))


def test_http_target_computes_cost_as_the_run_window_delta():
    target = AgentPlatformHttpTarget.from_client(_CostTrackingClient())
    t = target.run(Case(name="c", goal="x", expect=Expect()))
    assert t.cost_usd == pytest.approx(0.25)
    assert t.meta.get("cost_unavailable", False) is False


def test_http_target_returns_trajectory_when_costs_endpoint_fails():
    target = AgentPlatformHttpTarget.from_client(_FailingCostsClient())
    t = target.run(Case(name="nocost", goal="x", expect=Expect()))
    assert t.status == "completed"
    assert t.cost_usd == 0.0
    assert t.meta["cost_unavailable"] is True


def test_http_target_approve_flow_resumes_run():
    case = Case(
        name="approve",
        goal="send an email",
        expect=Expect(),
        planner=[
            '{"action": "tool", "tool": "send_email", "arguments": {"to": "a@b"}}',
            '{"action": "final", "answer": "sent"}',
        ],
        validator=['{"approved": true, "reason": "ok"}'],
    )

    orchestrator, approvals, executor, _side_effects, _calls = build_world(case)
    approved_client = TestClient(create_app(orchestrator, approvals, executor))
    approved_target = AgentPlatformHttpTarget.from_client(approved_client, approve=True)
    approved = approved_target.run(case)
    assert approved.meta["approved"] is True
    assert approved.meta["approval_id"]
    assert approved.status == "completed"
    assert approved.answer == "sent"

    orchestrator2, approvals2, executor2, _side_effects2, _calls2 = build_world(case)
    unapproved_client = TestClient(create_app(orchestrator2, approvals2, executor2))
    unapproved_target = AgentPlatformHttpTarget.from_client(unapproved_client, approve=False)
    unapproved = unapproved_target.run(case)
    assert unapproved.status == "waiting_approval"
    assert unapproved.meta["approved"] is False


class _EmptyRunsClient:
    """Stub client whose `POST /runs` answers 200 with an empty body, the
    shape the HTTP contract forbids and the target used to index into."""

    def get(self, url: str, **kw: Any) -> _StubResponse:
        if url == "/costs":
            return _StubResponse(json_data={"total_usd": 0.0})
        raise AssertionError(f"unexpected GET {url}")

    def post(self, url: str, **kw: Any) -> _StubResponse:
        if url == "/runs":
            return _StubResponse(json_data={})
        raise AssertionError(f"unexpected POST {url}")


def test_only_targets_that_watch_the_executor_claim_side_effects():
    assert "side_effects" in ScriptedTarget.capabilities
    assert "side_effects" in AgentPlatformLocalTarget.capabilities
    assert "side_effects" not in AgentPlatformHttpTarget.capabilities


def test_http_target_marks_side_effects_unobservable():
    target = AgentPlatformHttpTarget.from_client(TestClient(build_app()))
    t = target.run(Case(name="h", goal="say hi", expect=Expect()))
    assert t.meta["side_effects_unavailable"] is True


def test_http_target_names_the_missing_field_on_an_unexpected_body():
    """A 200 whose body does not match the documented run-record shape is a
    ValueError naming the response, not a bare KeyError."""
    target = AgentPlatformHttpTarget.from_client(_EmptyRunsClient())
    with pytest.raises(ValueError, match=r"POST /runs response lacks 'run_id'"):
        target.run(Case(name="empty", goal="x", expect=Expect()))
