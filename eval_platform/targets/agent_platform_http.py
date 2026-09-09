"""The agent platform over its HTTP surface: POST /runs, GET /runs/{id},
POST /approvals/{id}/approve. Works against a live server or, in tests,
against a FastAPI TestClient through from_client()."""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Callable
from typing import Any, Protocol

import httpx

from eval_platform.targets.base import TargetUnavailable
from eval_platform.targets.convert import run_dict_to_trajectory
from eval_platform.types import Case, Trajectory


class _Client(Protocol):
    """The subset of an HTTP client this target needs: enough to be
    satisfied by either `httpx.Client` or `fastapi.testclient.TestClient`.

    `get`/`post` are typed as `Callable[..., Any]` rather than as methods
    with a `**kw` catch-all: `httpx.Client` and `TestClient` each declare
    their real keyword arguments explicitly (no `**kwargs`), so a
    `**kw`-shaped method signature does not structurally match either one
    under pyright; `Callable[..., Any]` accepts both.
    """

    get: Callable[..., Any]
    post: Callable[..., Any]


class AgentPlatformHttpTarget:
    """Runs a `Case` against the agent platform's HTTP service.

    Talks to `/runs`, `/approvals`, and `/costs` on whatever client is
    given: a real `httpx.Client` against a live server, or, in tests, a
    `fastapi.testclient.TestClient` via `from_client()`, so the same code
    path is exercised in-process and over the wire.
    """

    name = "agent-platform-http"
    capabilities = frozenset({"agent", "approval"})

    def __init__(self, base_url: str, *, approve: bool = False, timeout_s: float = 30.0) -> None:
        """Connect to `base_url` and confirm the service is up.

        Raises `TargetUnavailable` if the server cannot be reached at all,
        or if `/health` responds with anything other than 200, so a caller
        can skip this target instead of failing every case against it.
        """
        self.approve = approve
        try:
            self._client: _Client = httpx.Client(base_url=base_url, timeout=timeout_s)
            r = self._client.get("/health")
        except httpx.HTTPError as e:
            raise TargetUnavailable(f"agent platform not reachable at {base_url}: {e}") from e
        if r.status_code != 200:
            raise TargetUnavailable(f"/health returned {r.status_code}")

    @classmethod
    def from_client(cls, client: _Client, *, approve: bool = False) -> AgentPlatformHttpTarget:
        """Build a target around an existing client (e.g. a FastAPI
        `TestClient`), bypassing the network `/health` check `__init__`
        does, since a test client is either already valid or not usable at
        all."""
        obj = cls.__new__(cls)
        obj.approve = approve
        obj._client = client
        return obj

    def run(self, case: Case) -> Trajectory:
        """Start a run for `case.goal`, optionally approve a pending gated
        action, and convert the resulting run record into a `Trajectory`.

        When `self.approve` is set and the run comes back `waiting_approval`,
        the first pending approval is approved and, if that resumes the run,
        the resumed record replaces the initial one. `meta["run_id"]` and
        `meta["approved"]` are always set so callers can trace the run and
        tell whether an approval happened.
        """
        start = time.perf_counter()
        r = self._client.post("/runs", json={"goal": case.goal})
        r.raise_for_status()
        record = r.json()
        approved = False
        if self.approve and record["status"] == "waiting_approval":
            pending = self._client.get("/approvals").json()
            if pending:
                a = self._client.post(f"/approvals/{pending[0]['id']}/approve")
                a.raise_for_status()
                resumed = a.json().get("resumed_run")
                if resumed:
                    record = resumed
                    approved = True
        wall_ms = (time.perf_counter() - start) * 1000.0
        costs = self._client.get("/costs").json()
        t = run_dict_to_trajectory(
            record,
            target=self.name,
            goal=case.goal,
            wall_ms=wall_ms,
            cost_usd=float(costs.get("total_usd", 0.0)),
        )
        return dataclasses.replace(
            t, meta={**t.meta, "run_id": record["run_id"], "approved": approved}
        )
