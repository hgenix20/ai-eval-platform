"""Content-addressed cache for judge verdicts (design spec 4.5).

Key = SHA-256 over (case id, output text, judge model id and version,
rubric id and version, grader parameters). A hit returns the stored
verdict with zero model calls, so a rerun is byte-identical and free.
The cache root is `.cache/judge/` locally (gitignored).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

_KEY = re.compile(r"^[0-9a-f]{64}$")


def cache_key(
    *,
    case_id: str,
    output: str,
    judge_model: str,
    judge_version: str,
    rubric_id: str,
    rubric_version: str,
    params: dict[str, Any],
) -> str:
    """SHA-256 hex of the canonical JSON of every input. `params` is
    serialized with sorted keys, so insertion order never changes the key."""
    payload = {
        "case_id": case_id,
        "output": output,
        "judge_model": judge_model,
        "judge_version": judge_version,
        "rubric_id": rubric_id,
        "rubric_version": rubric_version,
        "params": params,
    }
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def model_version(model_id: str) -> str:
    """The version string that goes into a cache key for `model_id`.

    `hf/<repo>` resolves to the snapshot hash Hugging Face recorded in
    `<HF_HUB_CACHE>/models--<org>--<name>/refs/main` (default cache
    `~/.cache/huggingface/hub`); raises FileNotFoundError when the weights
    have not been downloaded, since an unversioned judge must not be cached.
    `mockllm/...` is "mock". Any other id is returned unchanged: hosted ids
    carry their release date.
    """
    if model_id.startswith("mockllm/"):
        return "mock"
    if model_id.startswith("hf/"):
        repo = model_id[len("hf/") :].replace("/", "--")
        root = Path(
            os.environ.get("HF_HUB_CACHE") or Path.home() / ".cache" / "huggingface" / "hub"
        )
        ref = root / f"models--{repo}" / "refs" / "main"
        if not ref.exists():
            raise FileNotFoundError(f"no local snapshot for {model_id}: {ref} is missing")
        return ref.read_text(encoding="utf-8").strip()
    return model_id


class JudgeCache:
    """One JSON file per key under `root`. Keys are validated against the
    64-hex-character shape before they touch the filesystem, so a caller
    cannot turn a key into a path."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, key: str) -> Path:
        if not _KEY.match(key):
            raise ValueError(f"cache key is not a sha256 hex digest: {key!r}")
        return self.root / f"{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        """The stored verdict for `key`, or None for a miss.

        A file that does not parse, or that does not carry both `label` and
        `raw`, is a miss. A write cut short (an interrupted run, a full disk)
        leaves exactly that, and the caller's next model call rewrites the
        entry; reading it as a hit would hand `judge()` a payload with no
        label in it. Raises ValueError when `key` is not a sha256 digest.
        """
        p = self._path(key)
        if not p.exists():
            return None
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict) or "label" not in payload or "raw" not in payload:
            return None
        return payload

    def put(self, key: str, payload: dict[str, Any]) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
