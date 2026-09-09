"""Suite summaries as JSON on disk. One file per run under results/<suite>/,
and latest.json always points at the newest run for that suite."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from eval_platform.types import SuiteResult


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


def write_summary(result: SuiteResult, results_dir: Path) -> Path:
    """Write `result` as JSON under `results_dir/<suite>/<started_at-safe>-<target>.json`
    and copy it to `results_dir/<suite>/latest.json`. Creates the suite directory
    if it does not exist. If that filename is already taken (two runs in the
    same second), a `-2`, `-3`, ... suffix is added before `.json` until a
    free name is found. Returns the path of the timestamped file (not
    latest.json).
    """
    suite_dir = results_dir / result.suite
    suite_dir.mkdir(parents=True, exist_ok=True)
    stamp = result.started_at.replace(":", "").replace("+0000", "Z").replace("+00:00", "Z")
    path = _free_path(suite_dir, f"{stamp}-{result.target}")
    path.write_text(json.dumps(result.to_dict(), indent=2, default=str), encoding="utf-8")
    shutil.copyfile(path, suite_dir / "latest.json")
    return path


def read_summary(path: Path) -> dict[str, Any]:
    """Read a summary JSON file. Raises FileNotFoundError if `path` does not
    exist, or a json.JSONDecodeError if its content is not valid JSON.
    """
    return json.loads(path.read_text(encoding="utf-8"))


def latest_summary(results_dir: Path, suite: str) -> dict[str, Any] | None:
    """Read `results_dir/<suite>/latest.json` if it exists, else return None.
    Never raises for a missing suite directory or missing latest.json.
    """
    p = results_dir / suite / "latest.json"
    return read_summary(p) if p.exists() else None
