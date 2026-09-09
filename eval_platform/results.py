"""Suite summaries as JSON on disk. One file per run under results/<suite>/,
and latest.json always points at the newest run for that suite."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from eval_platform.types import SuiteResult


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


def write_summary(result: SuiteResult, results_dir: Path) -> Path:
    """Write `result` as JSON under `results_dir/<suite>/<started_at-safe>-<target-safe>.json`
    and copy it to `results_dir/<suite>/latest.json`. Creates the suite directory
    if it does not exist. If that filename is already taken (two runs in the
    same second), a `-2`, `-3`, ... suffix is added before `.json` until a
    free name is found. Returns the path of the timestamped file (not
    latest.json).

    Both the timestamp and the target are reduced to filename-legal
    characters first, so a target named after an Inspect model id
    ("anthropic/claude-haiku-4-5-20251001") writes one file inside the suite
    directory instead of failing on a directory that was never created. The
    file ends with a newline.
    """
    suite_dir = results_dir / result.suite
    suite_dir.mkdir(parents=True, exist_ok=True)
    stamp = result.started_at.replace(":", "").replace("+0000", "Z").replace("+00:00", "Z")
    path = _free_path(suite_dir, f"{_safe(stamp)}-{_safe(result.target)}")
    payload = json.dumps(result.to_dict(), indent=2, default=str) + "\n"
    path.write_text(payload, encoding="utf-8")
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
