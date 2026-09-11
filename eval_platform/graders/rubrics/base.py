from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from eval_platform.types import Case, Trajectory

# Character cap on the context block handed to a judge. Long tool outputs
# are truncated from the end with a marker, so a judge never sees an
# unbounded prompt and a 3B model's context window is respected.
CONTEXT_CHARS = 6000


def context_from(trajectory: Trajectory) -> str:
    """Every tool step's output, in order, joined by blank lines and capped
    at CONTEXT_CHARS. Empty string when the run made no tool call."""
    parts = [str(s.output) for s in trajectory.steps if s.kind == "tool" and s.output is not None]
    text = "\n\n".join(parts)
    if len(text) > CONTEXT_CHARS:
        text = text[:CONTEXT_CHARS] + "\n[truncated]"
    return text


@dataclass(frozen=True)
class Rubric:
    id: str
    version: str
    system: str
    labels: tuple[str, ...]
    passing: str
    failing: str
    build_user_prompt: Callable[[Case, Trajectory], str]

    def user_prompt(self, case: Case, trajectory: Trajectory) -> str:
        return self.build_user_prompt(case, trajectory)
