"""Judge rubrics: one per dimension, each with an id, a version, the
judge's instructions, and how a (case, trajectory) pair becomes the
user prompt. Edit a rubric's text and bump its version in the same
change; the version is part of the judge cache key."""

from __future__ import annotations

from .base import Rubric
from .correctness import CORRECTNESS
from .faithfulness import FAITHFULNESS

RUBRICS: dict[str, Rubric] = {FAITHFULNESS.id: FAITHFULNESS, CORRECTNESS.id: CORRECTNESS}

__all__ = ["CORRECTNESS", "FAITHFULNESS", "RUBRICS", "Rubric"]
