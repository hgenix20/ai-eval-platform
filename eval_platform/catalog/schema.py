"""Catalog entry contract. One YAML file per benchmark; the primary URL is the
registry key because benchmark names collide."""

from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

Category = Literal[
    "capability",
    "coding",
    "tool-use",
    "agent",
    "long-context",
    "retrieval",
    "hallucination",
    "safety",
    "injection",
    "judge",
]
LicenseStatus = Literal["verified", "ambiguous", "unverified", "non-commercial", "gated"]
Scoring = Literal["exact-match", "execution", "state", "classifier", "llm-judge", "human"]
RunnerKind = Literal["inspect_evals", "builtin", "external", "none"]
Status = Literal["current", "approaching-saturation", "saturated", "legacy", "held-out"]
CostClass = Literal["free", "low", "medium", "high"]

_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class License(BaseModel):
    """A benchmark's code and data licensing, and how confident we are in it.

    Contract: `status` records how firmly `code`/`data` have been verified,
    not the license text itself; downstream code (e.g. `CatalogEntry.runnable`)
    treats `status == "non-commercial"` as a hard block on running the eval.
    """

    model_config = ConfigDict(extra="forbid")
    code: str
    data: str
    status: LicenseStatus


class Runner(BaseModel):
    """How a benchmark is executed.

    Contract: `ref` is required for every `kind` except `"none"` (a
    catalog entry with no runnable harness yet). Failure mode: constructing
    a `Runner` with a non-`"none"` kind and no `ref` raises `ValueError` via
    the model validator below.
    """

    model_config = ConfigDict(extra="forbid")
    kind: RunnerKind
    ref: str | None = None

    @model_validator(mode="after")
    def _ref_required(self) -> Runner:
        if self.kind != "none" and not self.ref:
            raise ValueError("runner.ref is required unless runner.kind is none")
        return self


class CatalogEntry(BaseModel):
    """One benchmark's catalog record, loaded from a single YAML file.

    Contract: `extra="forbid"` so a typo'd or stale field raises a validation
    error instead of being dropped with no warning. `id` must be a slug
    (`^[a-z0-9][a-z0-9-]*$`); `sources` must carry at least one URL. The
    loader (`loader.load_catalog`) is responsible for cross-file invariants
    (duplicate id/url); this class only validates a single entry in
    isolation.
    """

    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=_SLUG.pattern)
    name: str
    url: HttpUrl
    category: Category
    maintainer: str
    size: str
    license: License
    scoring: Scoring
    runner: Runner
    status: Status
    cost_class: CostClass
    requires: list[str] = []
    verified: date
    sources: list[HttpUrl] = Field(min_length=1)
    notes: str = ""

    @property
    def runnable(self) -> bool:
        """Whether this entry can actually be executed by the platform.

        True only when the runner has a harness we can invoke
        (`inspect_evals` or `builtin`) and the license status is not
        `"non-commercial"`, regardless of how the runner is otherwise
        configured.
        """
        return (
            self.runner.kind in ("inspect_evals", "builtin")
            and self.license.status != "non-commercial"
        )
