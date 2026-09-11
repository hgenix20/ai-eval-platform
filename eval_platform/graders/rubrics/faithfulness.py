from __future__ import annotations

from eval_platform.types import Case, Trajectory

from .base import Rubric, context_from

_SYSTEM = """You are grading whether an answer is supported by the context it was given.
Read the context, then the answer. Every factual claim in the answer must be stated in or
follow directly from the context. Ignore whether the answer is helpful or complete.
Reply with your reasoning in at most three sentences, then a final line in exactly this form:
VERDICT: SUPPORTED
or
VERDICT: UNSUPPORTED
Use VERDICT: UNKNOWN only when the context is empty or the answer makes no factual claim."""


def _prompt(case: Case, trajectory: Trajectory) -> str:
    return (
        f"Question:\n{case.goal}\n\nContext:\n{context_from(trajectory) or '[no context]'}"
        f"\n\nAnswer:\n{trajectory.answer or ''}"
    )


FAITHFULNESS = Rubric(
    id="faithfulness",
    version="1",
    system=_SYSTEM,
    labels=("SUPPORTED", "UNSUPPORTED", "UNKNOWN"),
    passing="SUPPORTED",
    failing="UNSUPPORTED",
    build_user_prompt=_prompt,
)
