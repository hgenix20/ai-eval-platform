"""Suite summaries as JSON on disk. One file per run under results/<suite>/,
and latest.json always points at the newest run for that suite."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from eval_platform.types import CaseResult, Grade, Step, SuiteResult, Trajectory


def _safe(component: str) -> str:
    """Reduce one path component to characters that are legal in a filename
    on every supported platform. Inspect model ids carry a provider prefix
    ("anthropic/claude-haiku-4-5-20251001", "mockllm/model"), and the slash
    would otherwise be read as a directory separator pointing at a directory
    that does not exist.
    """
    return re.sub(r"[^A-Za-z0-9._-]", "_", component)


def _free_path(suite_dir: Path, stem: str) -> Path:
    """Find a filename in `suite_dir` that does not exist yet, based on
    `stem`. Returns `<stem>.json` if free; otherwise tries `<stem>-2.json`,
    `<stem>-3.json`, and so on, so two runs started in the same second do
    not overwrite each other.
    """
    candidate = suite_dir / f"{stem}.json"
    n = 2
    while candidate.exists():
        candidate = suite_dir / f"{stem}-{n}.json"
        n += 1
    return candidate


def write_summary(result: SuiteResult, results_dir: Path, *, promote_latest: bool = True) -> Path:
    """Write `result` as JSON under `results_dir/<suite>/<started_at-safe>-<target-safe>.json`
    and, when `promote_latest` is True, copy it to `results_dir/<suite>/latest.json`.
    Creates the suite directory if it does not exist. If that filename is
    already taken (two runs in the same second), a `-2`, `-3`, ... suffix
    is added before `.json` until a free name is found. Returns the path
    of the timestamped file (not latest.json).

    Both the timestamp and the target are reduced to filename-legal
    characters first, so a target named after an Inspect model id
    ("anthropic/claude-haiku-4-5-20251001") writes one file inside the suite
    directory instead of failing on a directory that was never created. The
    file ends with a newline.

    `promote_latest=False` writes the per-run file only and leaves
    `latest.json` exactly as it was (untouched if present, still absent if
    not). This is for a run that must be kept as a record without becoming
    the number the gate and report read: an errored Inspect run must not
    overwrite a prior successful measurement, or invent a fresh one, just
    because it happened to run most recently.
    """
    suite_dir = results_dir / result.suite
    suite_dir.mkdir(parents=True, exist_ok=True)
    stamp = result.started_at.replace(":", "").replace("+0000", "Z").replace("+00:00", "Z")
    path = _free_path(suite_dir, f"{_safe(stamp)}-{_safe(result.target)}")
    payload = json.dumps(result.to_dict(), indent=2, default=str) + "\n"
    path.write_text(payload, encoding="utf-8")
    if promote_latest:
        shutil.copyfile(path, suite_dir / "latest.json")
    return path


def read_summary(path: Path) -> dict[str, Any]:
    """Read a summary JSON file. Raises FileNotFoundError if `path` does not
    exist, or a json.JSONDecodeError if its content is not valid JSON.
    """
    return json.loads(path.read_text(encoding="utf-8"))


def _step(d: dict[str, Any]) -> Step:
    """One Step from the dict `SuiteResult.to_dict()` wrote for it."""
    return Step(
        kind=d["kind"],
        name=d["name"],
        input=d.get("input"),
        output=d.get("output"),
        latency_ms=float(d.get("latency_ms", 0.0)),
        tokens_in=int(d.get("tokens_in", 0)),
        tokens_out=int(d.get("tokens_out", 0)),
        cost_usd=float(d.get("cost_usd", 0.0)),
        error=d.get("error"),
    )


def _trajectory(d: dict[str, Any]) -> Trajectory:
    """One Trajectory from its dict form, steps and side effects included."""
    return Trajectory(
        target=d["target"],
        goal=d["goal"],
        steps=tuple(_step(s) for s in d["steps"]),
        status=d["status"],
        answer=d.get("answer"),
        side_effects=tuple(dict(x) for x in d.get("side_effects", ())),
        cost_usd=float(d["cost_usd"]),
        wall_ms=float(d["wall_ms"]),
        meta=dict(d.get("meta") or {}),
    )


def _case_result(d: dict[str, Any]) -> CaseResult:
    """One CaseResult from its dict form. Raises ValueError naming the case
    when a key it needs is missing or holds the wrong kind of value."""
    name = d.get("name", "<unnamed>")
    try:
        traj = d.get("trajectory")
        return CaseResult(
            name=d["name"],
            passed=bool(d["passed"]),
            grades=tuple(
                Grade(g["dimension"], float(g["value"]), bool(g["passed"]), g["explanation"])
                for g in d["grades"]
            ),
            trajectory=_trajectory(traj) if traj is not None else None,
            skipped_reason=d.get("skipped_reason"),
            kind=d.get("kind", "benign"),
        )
    except (AttributeError, KeyError, TypeError, ValueError) as e:
        raise ValueError(f"case {name}: malformed summary entry: {e}") from e


def summary_to_result(d: dict[str, Any]) -> SuiteResult:
    """Rebuild a SuiteResult from the dict `SuiteResult.to_dict()` produced,
    as `read_summary` hands it back: the inverse of that method, down to the
    tuples the dataclasses declare, so `summary_to_result(x).to_dict() == x`
    for any summary this package wrote.

    Failure mode: raises ValueError when the dict is not shaped like a
    summary, including a metric that is not a number. A bad case entry names
    the case in the message, so the caller can find the offending record in
    a file of hundreds.
    """
    try:
        cases = tuple(_case_result(c) for c in d["cases"])
    except (AttributeError, KeyError, TypeError) as e:
        raise ValueError(f"not a suite summary: {e}") from e
    try:
        return SuiteResult(
            suite=d["suite"],
            target=d["target"],
            started_at=d["started_at"],
            finished_at=d["finished_at"],
            cases=cases,
            metrics={k: float(v) for k, v in d["metrics"].items()},
            meta=dict(d.get("meta") or {}),
        )
    except (AttributeError, KeyError, TypeError, ValueError) as e:
        raise ValueError(f"not a suite summary: {e}") from e


def latest_summary(results_dir: Path, suite: str) -> dict[str, Any] | None:
    """Read `results_dir/<suite>/latest.json` if it exists, else return None.
    Never raises for a missing suite directory or missing latest.json.
    """
    p = results_dir / suite / "latest.json"
    return read_summary(p) if p.exists() else None
