"""Pure trajectory measures shared by the deterministic graders and metrics."""

from __future__ import annotations

import json
from collections.abc import Sequence

from eval_platform.types import Step


def _key(step: Step) -> str:
    payload = step.input if step.input is not None else {}
    return f"{step.name}:{json.dumps(payload, sort_keys=True, default=str)}"


def redundant_calls(steps: Sequence[Step]) -> int:
    """Count tool steps that repeat an earlier (tool, arguments) pair exactly."""
    seen: set[str] = set()
    repeats = 0
    for s in steps:
        if s.kind != "tool":
            continue
        k = _key(s)
        if k in seen:
            repeats += 1
        seen.add(k)
    return repeats


def step_efficiency(reference: int, used: int) -> float:
    """reference / used, capped at 1.0; 0.0 when the reference is not positive."""
    if reference <= 0:
        return 0.0
    if used <= reference:
        return 1.0
    return reference / used
