"""What a system under test looks like to the runner."""

from __future__ import annotations

from typing import Protocol

from eval_platform.types import Case, Trajectory


class TargetUnavailable(Exception):  # noqa: N818 -- name is a fixed cross-task interface, not renameable
    """The target cannot run here (server down, extra not installed, key missing).

    Raised by a target's constructor or its `run()` when the target's
    requirements are not met, so the caller can skip the case instead of
    failing the whole suite.
    """


class AgentTarget(Protocol):
    """A system under test: something that can attempt a `Case` and report
    what happened as a `Trajectory`.

    `name` identifies the target in results and reports. `capabilities` is
    the set of things this target can do (e.g. `{"agent"}`); a case only
    runs on a target whose `capabilities` is a superset of the case's
    `target_requirements`.
    """

    name: str
    capabilities: frozenset[str]

    def run(self, case: Case) -> Trajectory:
        """Attempt `case.goal` and return the resulting `Trajectory`.

        Raises `TargetUnavailable` if this target cannot run at all right
        now; raises `ValueError` if `case` is malformed for this target
        (e.g. missing a required field).
        """
        ...
