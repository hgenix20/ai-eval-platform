"""Spend and time bounds for a run, plus the append-only spend ledger.

A Budget is checked before every sample and charged after it. Exceeding it
raises BudgetExceeded; the caller stops the run, keeps partial results, and
marks the run budget_exceeded. The Ledger is the program-wide record that
makes the $150 ceiling visible across runs.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


class BudgetExceeded(Exception):  # noqa: N818 -- name is a fixed interface (see task brief), not renameable to *Error
    """Raised when a run has spent past its dollar or wall-clock ceiling.

    Attributes:
        reason: "usd" if the dollar ceiling was (or would be) exceeded,
            "wall" if the wall-clock ceiling was exceeded.

    The caller is expected to catch this, stop the run, keep whatever
    partial results exist, and mark the run as budget_exceeded.
    """

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"budget exceeded ({reason}): {detail}")
        self.reason = reason


@dataclass
class Budget:
    """Tracks spend and elapsed wall time against fixed ceilings for a run.

    Contract: call `check` before running a sample (optionally passing its
    projected cost) so an overrun is caught before the work happens, and
    call `charge` after the sample completes with its actual cost. Both
    methods raise BudgetExceeded on overrun; neither method is safe to
    ignore, since the run must stop on either.

    Not thread-safe: callers running samples concurrently must serialize
    access to a shared Budget instance themselves.
    """

    max_usd: float
    max_wall_s: float
    spent_usd: float = 0.0
    started: float = field(default_factory=time.monotonic)

    def remaining_usd(self) -> float:
        """Return the unspent dollar amount (may be negative if overspent)."""
        return self.max_usd - self.spent_usd

    def charge(self, usd: float) -> None:
        """Record actual spend of `usd` after a sample completes.

        Raises BudgetExceeded("usd") if the running total now exceeds
        max_usd. The charge is still recorded before the exception is
        raised, so remaining_usd reflects the true (over-budget) spend.
        """
        self.spent_usd += usd
        if self.spent_usd > self.max_usd:
            raise BudgetExceeded("usd", f"spent {self.spent_usd:.4f} of {self.max_usd:.4f}")

    def check(self, projected_next_usd: float = 0.0) -> None:
        """Raise before running the next sample if it would overrun a ceiling.

        Raises BudgetExceeded("wall") if elapsed time already exceeds
        max_wall_s, or BudgetExceeded("usd") if spent_usd plus
        `projected_next_usd` would exceed max_usd. Call this before
        starting a sample; it charges nothing.
        """
        elapsed = time.monotonic() - self.started
        if elapsed > self.max_wall_s:
            raise BudgetExceeded("wall", f"{elapsed:.0f}s elapsed of {self.max_wall_s:.0f}s")
        if self.spent_usd + projected_next_usd > self.max_usd:
            raise BudgetExceeded(
                "usd", f"next sample would reach {self.spent_usd + projected_next_usd:.4f}"
            )


class Ledger:
    """Append-only JSON-lines record of spend across runs.

    Each `record` call appends one JSON object as a line; the file is
    never rewritten, so concurrent writers from separate processes each
    append complete lines without needing to coordinate a shared lock.
    `total_usd` re-reads the file each time, so it always reflects spend
    recorded by any process, not just this instance.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def record(self, *, run_id: str, suite: str, target: str, usd: float, note: str = "") -> None:
        """Append one spend entry with a UTC timestamp.

        Creates the parent directory if missing. Failure mode: if `path`
        exists but is not writable, this raises OSError from the
        underlying file open.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = {
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
            "run_id": run_id,
            "suite": suite,
            "target": target,
            "usd": round(usd, 6),
            "note": note,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")

    def total_usd(self) -> float:
        """Return the sum of all recorded usd amounts, or 0.0 if the ledger file does not exist."""
        if not self.path.exists():
            return 0.0
        total = 0.0
        for raw in self.path.read_text(encoding="utf-8").splitlines():
            if raw.strip():
                total += float(json.loads(raw)["usd"])
        return total
