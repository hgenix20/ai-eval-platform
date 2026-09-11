"""The published enterprise-agent-platform, in process, with scripted model
providers. This is the free, deterministic system under test for the offline
ladder, and it builds the same world the agent platform's own eval runner did."""

from __future__ import annotations

import time
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from eval_platform.targets.base import TargetUnavailable
from eval_platform.targets.convert import run_dict_to_trajectory
from eval_platform.types import Case, Trajectory

# Imported unconditionally only for static type checking: pyright resolves
# names from the `if TYPE_CHECKING` branch, so the class body below type-checks
# as if the import always succeeds, while the `else` branch below is what
# actually runs and records whether it did. This keeps `agent_platform`
# genuinely optional at import time (see the module docstring's contract)
# without pyright treating every name used later as possibly unbound.
if TYPE_CHECKING:
    from agent_platform.approvals import ApprovalQueue
    from agent_platform.gateway import CostMeter, Gateway, Route, RouteStep
    from agent_platform.gateway.providers import FakeProvider
    from agent_platform.memory import DeterministicEmbedder, InMemoryMemoryStore, memory_tools
    from agent_platform.orchestration import Orchestrator
    from agent_platform.tools import AgentGrant, ToolExecutor, ToolRegistry, ToolSpec

    from eval_platform.targets.faults import (
        FaultLedger,
        fallback_route,
        wrap_provider,
        wrap_tool_handler,
    )

    _IMPORT_ERROR: ImportError | None = None
else:
    try:
        from agent_platform.approvals import ApprovalQueue
        from agent_platform.gateway import CostMeter, Gateway, Route, RouteStep
        from agent_platform.gateway.providers import FakeProvider
        from agent_platform.memory import DeterministicEmbedder, InMemoryMemoryStore, memory_tools
        from agent_platform.orchestration import Orchestrator
        from agent_platform.tools import AgentGrant, ToolExecutor, ToolRegistry, ToolSpec

        from eval_platform.targets.faults import (
            FaultLedger,
            fallback_route,
            wrap_provider,
            wrap_tool_handler,
        )
    except ImportError as e:  # pragma: no cover - exercised only without the extra
        _IMPORT_ERROR: ImportError | None = e
    else:
        _IMPORT_ERROR = None


def build_world(
    case: Case,
) -> tuple[
    Orchestrator,
    ApprovalQueue,
    ToolExecutor,
    list[dict[str, Any]],
    list[dict[str, Any]],
    FaultLedger,
]:
    """Build one tool registry, approval queue, executor, gateway, and
    orchestrator for `case`.

    Module-level (not a method) so it has two callers that must stay in
    sync: `AgentPlatformLocalTarget._world`, and tests that need this same
    world wired into a real FastAPI app via `agent_platform.service.create_app`
    to exercise `AgentPlatformHttpTarget`'s approval flow end to end. A fresh
    world per case keeps runs isolated: no shared memory, approval, or cost
    state leaks between cases in the same suite.

    Every registered tool is wrapped by `recorded` so its handler appends
    `{"tool": name, "arguments": args}` to `calls` when it actually runs.
    A gated tool (`send_email`) that parks waiting for approval never
    reaches its handler, so it leaves no entry in `calls`; the converter
    reads this list to fill in `Step.input` for the trajectory's tool steps.
    `recorded` runs first, so a tool call that a fault turns into a raised
    exception is still recorded as having been called.

    `case.faults` are wired in last, over the recorded tool specs and the
    scripted providers, through the shared `FaultLedger` returned as the
    sixth element. When any fault is a retryable provider fault, the
    "reason" route (the planner's route) gains a second step to a
    "fallback" provider that replays the same scripted planner responses;
    a retryable fault on the validator has no fallback.
    """
    side_effects: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    ledger = FaultLedger()

    def recorded(spec: ToolSpec) -> ToolSpec:
        def handler(args: dict) -> Any:
            calls.append({"tool": spec.name, "arguments": dict(args)})
            return spec.handler(args)

        return replace(spec, handler=handler)

    def registered(spec: ToolSpec) -> ToolSpec:
        return wrap_tool_handler(recorded(spec), case.faults, ledger)

    registry = ToolRegistry()
    registry.register(
        registered(
            ToolSpec(
                name="lookup",
                description="Look up a fact by key",
                input_schema={"type": "object", "properties": {"key": {"type": "string"}}},
                handler=lambda args: f"value-for-{args.get('key', '')}",
            )
        )
    )
    registry.register(
        registered(
            ToolSpec(
                name="send_email",
                description="Send an outbound email",
                input_schema={"type": "object", "properties": {"to": {"type": "string"}}},
                handler=lambda args: side_effects.append(args) or "sent",
                requires_approval=True,
            )
        )
    )
    store = InMemoryMemoryStore(DeterministicEmbedder())
    for spec in memory_tools(store, "eval-agent"):
        registry.register(registered(spec))
    approvals = ApprovalQueue()
    executor = ToolExecutor(registry, approvals)
    providers: dict[str, Any] = {
        "planner": wrap_provider(
            FakeProvider(name="planner", responses=list(case.planner), text="{}"),
            case.faults,
            ledger,
        ),
        "validator": wrap_provider(
            FakeProvider(name="validator", responses=list(case.validator), text="{}"),
            case.faults,
            ledger,
        ),
    }
    reason_steps = (RouteStep("planner", "planner-model"),)
    if fallback_route(case):
        providers["fallback"] = FakeProvider(
            name="fallback", responses=list(case.planner), text="{}"
        )
        reason_steps = (
            RouteStep("planner", "planner-model"),
            RouteStep("fallback", "fallback-model"),
        )
    gateway = Gateway(
        providers=providers,
        routes={
            "reason": Route(reason_steps),
            "draft": Route((RouteStep("validator", "validator-model"),)),
        },
        meter=CostMeter(prices={}),
    )
    orchestrator = Orchestrator(
        gateway=gateway,
        executor=executor,
        registry=registry,
        grant=AgentGrant.of("eval-agent", "lookup", "send_email", "remember", "recall"),
        max_steps=case.max_steps,
    )
    return orchestrator, approvals, executor, side_effects, calls, ledger


class AgentPlatformLocalTarget:
    """Runs a `Case` through the real agent platform orchestrator in process.

    The planner and validator are `FakeProvider`s scripted from
    `case.planner` / `case.validator`, so the run is deterministic and free.
    The world (tool registry, memory store, approval queue) mirrors the
    agent platform's own eval runner (`agent_platform/evals/runner.py`) so a
    case behaves the same way here as it does in that project's own suite.

    Raises `TargetUnavailable` at construction time if `agent_platform` is
    not importable (the `agent-platform` extra is not installed).
    """

    name = "agent-platform-local"
    capabilities = frozenset({"agent", "memory", "approval", "side_effects"})

    def __init__(self) -> None:
        if _IMPORT_ERROR is not None:
            raise TargetUnavailable("install the agent-platform extra") from _IMPORT_ERROR

    def _world(
        self, case: Case
    ) -> tuple[Orchestrator, list[dict[str, Any]], list[dict[str, Any]], FaultLedger]:
        """Build one orchestrator plus its side-effect sink, recorded tool
        calls, and fault ledger for `case`.

        Thin wrapper over the module-level `build_world`: this target has no
        use for the approval queue or executor it also builds (those are
        only needed to wire an HTTP service around the same world), so it
        drops them here.
        """
        orchestrator, _approvals, _executor, side_effects, calls, ledger = build_world(case)
        return orchestrator, side_effects, calls, ledger

    def run(self, case: Case) -> Trajectory:
        """Run `case.goal` through a fresh orchestrator and convert the
        agent platform's run dict into a `Trajectory`. Wall time is measured
        around the orchestrator call only, and cost is read from the
        gateway's cost meter after the run completes.

        A tool `raise` fault propagates out of the executor, and a fatal
        provider fault propagates out of the gateway as `ProviderError` or
        `AllProvidersFailedError`; either aborts `orchestrator.run` with an
        exception rather than an ordinary failed outcome. That exception is
        caught here (never in the platform) and turned into a Trajectory
        with `status="target_error"`, `answer=None`, no steps, and
        `meta["error"]` set to `repr(e)`; this is the honest record of an
        unrecovered fault, not a masked one. `meta["faults_fired"]` is set
        either way, from the run's `FaultLedger`.
        """
        orchestrator, side_effects, calls, ledger = self._world(case)
        start = time.perf_counter()
        try:
            result = orchestrator.run(case.goal)
        except Exception as e:
            wall_ms = (time.perf_counter() - start) * 1000.0
            return Trajectory(
                target=self.name,
                goal=case.goal,
                steps=(),
                status="target_error",
                answer=None,
                side_effects=tuple(side_effects),
                cost_usd=float(orchestrator.gateway.meter.snapshot()["total_usd"]),
                wall_ms=wall_ms,
                meta={"error": repr(e), "faults_fired": ledger.fired, "history_types": []},
            )
        wall_ms = (time.perf_counter() - start) * 1000.0
        trajectory = run_dict_to_trajectory(
            result,
            target=self.name,
            goal=case.goal,
            wall_ms=wall_ms,
            cost_usd=float(orchestrator.gateway.meter.snapshot()["total_usd"]),
            side_effects=side_effects,
            tool_calls=calls,
        )
        trajectory.meta["faults_fired"] = ledger.fired
        return trajectory
