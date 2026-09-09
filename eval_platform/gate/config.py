"""Gate configuration: what thresholds each suite must meet to pass regression
review. Loaded from YAML and validated strictly, so a typo in a threshold key
fails loudly instead of being ignored."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError


class Threshold(BaseModel):
    """One suite's pass criteria, checked against a single named metric.

    `min`/`max` are absolute bounds on the current value. `max_drop`,
    `max_rise`, and `max_increase_pct` are relative bounds against a baseline
    and are reported as not_measured when no baseline is available. Any
    combination of these may be set; none are required. Unknown fields are
    rejected (extra="forbid") so a misspelled key fails to load with an error
    instead of being ignored.
    """

    model_config = ConfigDict(extra="forbid")
    metric: str
    min: float | None = None
    max: float | None = None
    max_drop: float | None = None
    max_rise: float | None = None
    max_increase_pct: float | None = None


class GateConfig(BaseModel):
    """The full gate: one Threshold per suite, plus the PR sample size used
    by cheaper CI runs. Unknown top-level fields are rejected."""

    model_config = ConfigDict(extra="forbid")
    suites: dict[str, Threshold]
    pr_sample: int = 20


def load_gate_config(path: Path) -> GateConfig:
    """Load and validate a gate config YAML file.

    Failure modes: raises ValueError (wrapping the underlying
    pydantic.ValidationError) if the file's content does not match
    GateConfig's schema, for example an unknown key or a wrong type.
    Raises FileNotFoundError if `path` does not exist, and
    yaml.YAMLError if the content is not valid YAML.
    """
    try:
        return GateConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except ValidationError as e:
        raise ValueError(f"{path.name}: {e}") from e
