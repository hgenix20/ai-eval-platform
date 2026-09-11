"""Judge calibration against human labels (design spec 4.5).

A judge may contribute to the gate only after its Cohen's kappa against
the labeled set clears the floor and its verdicts agree with a second
judge model on at least the configured share of items. Everything here
is arithmetic over labels; the judges do the model calls through their
own cache.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator

from eval_platform.graders.hhem import HHEMGrader
from eval_platform.graders.judge import JudgeGrader
from eval_platform.types import Case, Expect, Step, Trajectory

Label = Literal["supported", "unsupported"]


class CalibrationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    context: str
    question: str = ""
    response: str
    label: Label
    provenance: dict[str, str]


def load_items(directory: Path) -> list[CalibrationItem]:
    """Every `*.jsonl` under `directory`, in sorted file order, one item per
    line. Raises ValueError on a duplicate id or an invalid row (with the
    file and line number), FileNotFoundError when the directory is missing."""
    if not directory.is_dir():
        raise FileNotFoundError(f"calibration directory {directory} does not exist")
    items: list[CalibrationItem] = []
    seen: set[str] = set()
    for path in sorted(directory.glob("*.jsonl")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                item = CalibrationItem.model_validate_json(line)
            except ValueError as e:
                raise ValueError(f"{path.name}:{n}: {e}") from e
            if item.id in seen:
                raise ValueError(f"{path.name}:{n}: duplicate id {item.id!r}")
            seen.add(item.id)
            items.append(item)
    return items


def cohen_kappa(a: Sequence[str], b: Sequence[str]) -> float:
    """Cohen's kappa between two label sequences of equal length. Returns
    0.0 when expected agreement is 1.0 (both raters constant), where the
    statistic is undefined. Raises ValueError on a length mismatch or
    empty input."""
    if len(a) != len(b) or not a:
        raise ValueError("kappa needs two equal-length, non-empty label sequences")
    n = len(a)
    observed = sum(1 for x, y in zip(a, b, strict=True) if x == y) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    if expected == 1.0:
        return 0.0
    return (observed - expected) / (1.0 - expected)


def agreement(a: Sequence[str], b: Sequence[str]) -> float:
    """Share of positions where the two sequences carry the same label."""
    if len(a) != len(b) or not a:
        raise ValueError("agreement needs two equal-length, non-empty label sequences")
    return sum(1 for x, y in zip(a, b, strict=True) if x == y) / len(a)


@dataclass(frozen=True)
class JudgeCalibration:
    judge: str
    version: str
    items: int
    unknown: int
    kappa: float
    accuracy: float
    tp: int
    fp: int
    tn: int
    fn: int


@dataclass(frozen=True)
class CalibrationReport:
    started_at: str
    finished_at: str
    items: int
    judges: tuple[JudgeCalibration, ...]
    swap_agreement: float | None
    swap_pair: tuple[str, str] | None
    kappa_floor: float
    min_swap_agreement: float

    def calibrated(self, judge: str) -> tuple[bool, str]:
        """Whether `judge` may block the gate, with the reason either way."""
        match = [j for j in self.judges if j.judge == judge]
        if not match:
            return False, f"judge {judge} not in the calibration report"
        j = match[0]
        if j.kappa < self.kappa_floor:
            return False, f"kappa {j.kappa:.2f} < {self.kappa_floor:.2f}"
        if self.swap_agreement is None:
            return True, (
                f"kappa {j.kappa:.2f} >= {self.kappa_floor:.2f}; "
                "single judge, swap agreement not measured"
            )
        if self.swap_agreement < self.min_swap_agreement:
            return (
                False,
                f"swap agreement {self.swap_agreement:.2f} < {self.min_swap_agreement:.2f}",
            )
        return True, (
            f"kappa {j.kappa:.2f} >= {self.kappa_floor:.2f}; "
            f"swap agreement {self.swap_agreement:.2f} >= {self.min_swap_agreement:.2f}"
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["calibrated"] = {j.judge: list(self.calibrated(j.judge)) for j in self.judges}
        return d


def _as_case(item: CalibrationItem) -> tuple[Case, Trajectory]:
    case = Case(name=item.id, goal=item.question or "Summarize the document.", expect=Expect())
    traj = Trajectory(
        target="calibration",
        goal=case.goal,
        status="completed",
        answer=item.response,
        steps=(Step("tool", "context", {}, item.context),),
        side_effects=(),
        cost_usd=0.0,
        wall_ms=0.0,
    )
    return case, traj


def _labels_for(judge: JudgeGrader | HHEMGrader, items: Sequence[CalibrationItem]) -> list[str]:
    out: list[str] = []
    for item in items:
        case, traj = _as_case(item)
        if isinstance(judge, HHEMGrader):
            g = judge.grade(case, traj)
            out.append("supported" if g.passed else "unsupported")
            continue
        r = judge.judge(case, traj)
        # "pass" here is a Verdict literal, not a credential; bandit's B105
        # heuristic matches the dict key string regardless (see judge.py).
        out.append({"pass": "supported", "fail": "unsupported"}.get(r.verdict, "unknown"))  # nosec B105
    return out


def _score(judge_id: str, version: str, truth: list[str], got: list[str]) -> JudgeCalibration:
    pairs = [(t, g) for t, g in zip(truth, got, strict=True) if g != "unknown"]
    unknown = len(got) - len(pairs)
    if not pairs:
        return JudgeCalibration(judge_id, version, len(got), unknown, 0.0, 0.0, 0, 0, 0, 0)
    t, g = [p[0] for p in pairs], [p[1] for p in pairs]
    tp = sum(1 for x, y in pairs if x == "unsupported" and y == "unsupported")
    tn = sum(1 for x, y in pairs if x == "supported" and y == "supported")
    fp = sum(1 for x, y in pairs if x == "supported" and y == "unsupported")
    fn = sum(1 for x, y in pairs if x == "unsupported" and y == "supported")
    return JudgeCalibration(
        judge_id, version, len(got), unknown, cohen_kappa(t, g), agreement(t, g), tp, fp, tn, fn
    )


def calibrate(
    items: Sequence[CalibrationItem],
    judges: Sequence[JudgeGrader],
    *,
    kappa_floor: float = 0.70,
    min_swap_agreement: float = 0.90,
    hhem: HHEMGrader | None = None,
) -> CalibrationReport:
    """Run every judge (and HHEM when given) over `items`; kappa and
    accuracy are computed over the items the judge labeled (unknowns
    excluded and counted). Swap agreement is between the first two judges
    in `judges`, over items where both gave a label; None with one judge."""
    started = datetime.now(UTC).isoformat(timespec="seconds")
    truth = [i.label for i in items]
    rows: list[JudgeCalibration] = []
    labels: dict[str, list[str]] = {}
    for j in judges:
        labels[j.id] = _labels_for(j, items)
        rows.append(_score(j.id, j.version, truth, labels[j.id]))
    if hhem is not None:
        got = _labels_for(hhem, items)
        rows.append(_score(hhem.id, hhem.version, truth, got))
    swap: float | None = None
    pair: tuple[str, str] | None = None
    if len(judges) >= 2:
        a, b = judges[0].id, judges[1].id
        both = [
            (x, y) for x, y in zip(labels[a], labels[b], strict=True) if "unknown" not in (x, y)
        ]
        swap = agreement([x for x, _ in both], [y for _, y in both]) if both else 0.0
        pair = (a, b)
    return CalibrationReport(
        started,
        datetime.now(UTC).isoformat(timespec="seconds"),
        len(items),
        tuple(rows),
        swap,
        pair,
        kappa_floor,
        min_swap_agreement,
    )


class JudgeCalibrationRow(BaseModel):
    """One judge's row as `write_report` serializes `JudgeCalibration`."""

    model_config = ConfigDict(extra="forbid")
    judge: str
    version: str
    items: int
    unknown: int
    kappa: float
    accuracy: float
    tp: int
    fp: int
    tn: int
    fn: int


class CalibrationReportFile(BaseModel):
    """The on-disk shape of `results/calibration/latest.json`, which is
    `CalibrationReport.to_dict()` written as JSON.

    This is the contract a reader may rely on, and `evalplat calibrate
    --check` is what enforces it without a model call: CI has no GPU and no
    hosted credits, so the committed report is the only calibration evidence
    a build can read. `calibrated` carries `[ok, reason]` per judge, and
    every judge in `judges` must appear there, since a row with no verdict
    would leave a reader guessing whether the judge may gate.
    """

    model_config = ConfigDict(extra="forbid")
    started_at: str
    finished_at: str
    items: int
    judges: list[JudgeCalibrationRow]
    swap_agreement: float | None
    swap_pair: tuple[str, str] | None
    kappa_floor: float
    min_swap_agreement: float
    calibrated: dict[str, tuple[bool, str]]

    @model_validator(mode="after")
    def _every_judge_carries_a_verdict(self) -> CalibrationReportFile:
        missing = sorted(j.judge for j in self.judges if j.judge not in self.calibrated)
        if missing:
            raise ValueError(f"calibrated verdict missing for {', '.join(missing)}")
        return self


def load_report(path: Path) -> CalibrationReportFile:
    """Read and validate a written calibration report.

    Raises OSError when `path` cannot be read (FileNotFoundError included)
    and ValueError when its content is not a valid report, so a caller can
    tell a missing file from a malformed one by exception type.
    """
    return CalibrationReportFile.model_validate_json(path.read_text(encoding="utf-8"))


def write_report(report: CalibrationReport, results_dir: Path) -> Path:
    """Write `results/calibration/<started_at-safe>.json` and copy it to
    `latest.json`. Returns the timestamped path."""
    out = results_dir / "calibration"
    out.mkdir(parents=True, exist_ok=True)
    stem = report.started_at.replace(":", "").replace("+00:00", "Z")
    path = out / f"{stem}.json"
    text = json.dumps(report.to_dict(), indent=2) + "\n"
    path.write_text(text, encoding="utf-8")
    (out / "latest.json").write_text(text, encoding="utf-8")
    return path
