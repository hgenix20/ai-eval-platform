from __future__ import annotations

from eval_platform.types import Case, Trajectory

from .base import Rubric

_SYSTEM = """You are grading a short answer against a reference answer.
CORRECT means the answer states the same fact as the reference, with no contradicting claim.
INCORRECT means the answer states a fact that contradicts the reference.
NOT_ATTEMPTED means the answer declines, hedges without committing, or does not address the
question.
Reply with your reasoning in at most three sentences, then a final line in exactly this form:
VERDICT: CORRECT
or
VERDICT: INCORRECT
or
VERDICT: NOT_ATTEMPTED"""


def _prompt(case: Case, trajectory: Trajectory) -> str:
    reference = case.expect.answer_contains or "[no reference]"
    return (
        f"Question:\n{case.goal}\n\nReference answer:\n{reference}"
        f"\n\nAnswer:\n{trajectory.answer or ''}"
    )


CORRECTNESS = Rubric(
    id="correctness",
    version="1",
    system=_SYSTEM,
    labels=("CORRECT", "INCORRECT", "NOT_ATTEMPTED"),
    passing="CORRECT",
    failing="INCORRECT",
    build_user_prompt=_prompt,
)
