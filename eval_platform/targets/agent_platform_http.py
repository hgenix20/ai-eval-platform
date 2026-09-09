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

    Every request `run()` makes is wrapped so an HTTP-status or transport
    failure raises `ValueError`, not a raw `httpx` exception: `AgentTarget`
    implementations are only allowed to raise `TargetUnavailable` (server
    not reachable at all, checked once at construction) or `ValueError`
    (case malformed, or the running service rejected the request), so a
    stray `httpx.HTTPStatusError`/`httpx.HTTPError` escaping `run()` would
    violate that contract.
    """

    name = "agent-platform-http"
    capabilities = frozenset({"agent", "approval"})

    def __init__(self, base_url: str, *, approve: bool = False, timeout_s: float = 30.0) -> None:
        """Connect to `base_url` and confirm the service is up.

        Raises `TargetUnavailable` if the server cannot be reached at all,
        or if `/health` responds with anything other than 200, so a caller
        can skip this target instead of failing every case against it. On
        either failure path the client is closed before the exception
        propagates, so a target that never gets used doesn't leak its
        connection.
        """
        self.approve = approve
        client = httpx.Client(base_url=base_url, timeout=timeout_s)
        self._client: _Client = client
        try:
            r = client.get("/health")
        except httpx.HTTPError as e:
            client.close()
            raise TargetUnavailable(f"agent platform not reachable at {base_url}: {e}") from e
        if r.status_code != 200:
            client.close()
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

    def close(self) -> None:
        """Release the underlying network client's resources.

        Closes the client only when it is an `httpx.Client` this target
        opened itself (the `__init__` path); a client handed in through
        `from_client` (a `TestClient`, a test stub) has a lifecycle this
        target does not own, so it is left alone.
        """
        if isinstance(self._client, httpx.Client):
            self._client.close()

    def __enter__(self) -> AgentPlatformHttpTarget:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _request(self, method: str, path: str, **kw: Any) -> Any:
        """Issue one `method` call to `path` and return the raw response.

        Converts `httpx.HTTPStatusError` (the service answered with a 4xx/5xx)
        and `httpx.HTTPError` (the request never got a response at all) into
        `ValueError`, so every failure mode `run()` can hit crosses the
        `AgentTarget` boundary as the one exception type callers are
        contracted to expect from a malformed or rejected case.
        """
        call = self._client.get if method == "GET" else self._client.post
        try:
            r = call(path, **kw)
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            body = e.response.text
            raise ValueError(
                f"agent platform {method} {path} returned {e.response.status_code}: {body[:200]}"
            ) from e
        except httpx.HTTPError as e:
            raise ValueError(f"agent platform {method} {path} failed: {e}") from e
        return r

    def run(self, case: Case) -> Trajectory:
        """Start a run for `case.goal`, optionally approve a pending gated
        action, and convert the resulting run record into a `Trajectory`.

        When `self.approve` is set and the run comes back `waiting_approval`,
        the *newest* pending approval (by `created_at`) is approved and, if
        that resumes the run, the resumed record replaces the initial one.
        Selecting by newest is correct for one client driving one run at a
        time, which is this target's only use (the eval runner runs cases
        sequentially against a target); a server fielding several clients'
        runs concurrently would need the platform to report which approval
        belongs to which run (an `approval_id` on the run record) for this
        to stay correct, and it does not today. If no approval is pending
        when expected, `meta["approved"]` stays `False` and the run is not
        failed for it.

        `cost_usd` is the delta in the service's `/costs` `total_usd`
        between just before `POST /runs` and just after the run (and any
        approval) finishes, clamped at 0.0, since `/costs` is a process-wide
        cumulative meter and other activity on the same server between two
        calls must not be charged to this run.

        `meta["run_id"]`, `meta["approved"]`, and `meta["approval_id"]`
        (`None` when no approval happened) are always set so callers can
        trace the run and tell whether, and through which approval, it
        resumed.
        """
        cost_before = float(self._request("GET", "/costs").json().get("total_usd", 0.0))
        start = time.perf_counter()
        record = self._request("POST", "/runs", json={"goal": case.goal}).json()
        approved = False
        approval_id: str | None = None
        if self.approve and record["status"] == "waiting_approval":
            pending = self._request("GET", "/approvals").json()
            if pending:
                newest = max(pending, key=lambda p: p["created_at"])
                approval = self._request("POST", f"/approvals/{newest['id']}/approve")
                resumed = approval.json().get("resumed_run")
                if resumed:
                    record = resumed
                    approved = True
                    approval_id = newest["id"]
        wall_ms = (time.perf_counter() - start) * 1000.0
        cost_after = float(self._request("GET", "/costs").json().get("total_usd", 0.0))
        t = run_dict_to_trajectory(
            record,
            target=self.name,
            goal=case.goal,
            wall_ms=wall_ms,
            cost_usd=max(0.0, cost_after - cost_before),
        )
        return dataclasses.replace(
            t,
            meta={
                **t.meta,
                "run_id": record["run_id"],
                "approved": approved,
                "approval_id": approval_id,
            },
        )
