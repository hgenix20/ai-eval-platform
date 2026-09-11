"""Fault injection for the in-process agent platform world.

A fault wraps one seam (a tool handler or a scripted provider) and misbehaves
for the first `times` calls, recording each firing in a FaultLedger so the
grader can tell whether the run recovered from a fault that actually
happened. Faults are deterministic: they fire in call order, never at
random.

Imported only from `agent_platform_local.py`, which itself imports
`agent_platform` only inside its own optional-dependency guard, so this
module's unconditional `agent_platform` imports never run when the
`agent-platform` extra is not installed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Any

from agent_platform.gateway.providers import FakeProvider
from agent_platform.gateway.types import ModelRequest, ModelResponse, ProviderError
from agent_platform.tools import ToolSpec

from eval_platform.types import Case, Fault


@dataclass
class FaultLedger:
    """Records every fault firing, in the order faults actually fired."""

    fired: list[dict[str, Any]] = field(default_factory=list)

    def record(self, fault: Fault, call_index: int) -> None:
        self.fired.append(
            {"at": fault.at, "name": fault.name, "kind": fault.kind, "call_index": call_index}
        )


def _matching(faults: list[Fault], at: str, name: str) -> list[Fault]:
    return [f for f in faults if f.at == at and f.name == name]


def wrap_tool_handler(spec: ToolSpec, faults: list[Fault], ledger: FaultLedger) -> ToolSpec:
    """Return a ToolSpec whose handler misbehaves per `faults` matching
    `spec.name`, for the first `times` calls of each matching fault, then
    falls through to the real handler. Returns `spec` unchanged when no
    fault targets this tool. The `malformed` kind returns the literal
    marker string "<<malformed>>" rather than a structured bad value,
    because the platform passes tool output to the model as plain text,
    with no rendering layer in between for a structured value to exercise.
    """
    mine = _matching(faults, "tool", spec.name)
    if not mine:
        return spec
    counter = {"n": 0}

    def handler(args: dict) -> Any:
        i = counter["n"]
        counter["n"] += 1
        for f in mine:
            if i < f.times:
                ledger.record(f, i)
                if f.kind == "raise":
                    raise RuntimeError(f"injected tool failure in {spec.name}")
                if f.kind == "malformed":
                    return "<<malformed>>"
                if f.kind == "empty":
                    return ""
                if f.kind == "delay":
                    time.sleep(f.delay_ms / 1000.0)
                    return spec.handler(args)
        return spec.handler(args)

    return replace(spec, handler=handler)


class FaultyProvider:
    """Wraps a FakeProvider so it misbehaves per `faults` for the first
    `times` calls of each matching fault, then falls through to the real
    provider. `.name` mirrors the wrapped provider's name so routing and
    grading code cannot tell a faulty provider from the real one by name.
    """

    def __init__(self, inner: FakeProvider, faults: list[Fault], ledger: FaultLedger) -> None:
        self.name = inner.name
        self._inner = inner
        self._faults = faults
        self._ledger = ledger
        self._calls = 0

    def complete(self, model: str, request: ModelRequest) -> ModelResponse:
        i = self._calls
        self._calls += 1
        for f in self._faults:
            if i < f.times:
                self._ledger.record(f, i)
                if f.kind == "retryable_error":
                    raise ProviderError("injected retryable provider failure", retryable=True)
                if f.kind == "fatal_error":
                    raise ProviderError("injected fatal provider failure", retryable=False)
                if f.kind == "delay":
                    time.sleep(f.delay_ms / 1000.0)
                    return self._inner.complete(model, request)
                if f.kind == "truncated":
                    response = self._inner.complete(model, request)
                    return replace(response, text=response.text[:12])
        return self._inner.complete(model, request)


def wrap_provider(
    provider: FakeProvider, faults: list[Fault], ledger: FaultLedger
) -> FakeProvider | FaultyProvider:
    """Return a FaultyProvider wrapping `provider` when a fault targets its
    name, else `provider` unchanged."""
    mine = _matching(faults, "provider", provider.name)
    return FaultyProvider(provider, mine, ledger) if mine else provider


def fallback_route(case: Case) -> bool:
    """True when the case injects a retryable provider fault, meaning the
    "reason" route needs a second (fallback) step for the planner to fall
    back to. The fallback route applies to "reason" (the planner's route)
    only; a retryable fault on the validator has no fallback route."""
    return any(f.at == "provider" and f.kind == "retryable_error" for f in case.faults)
