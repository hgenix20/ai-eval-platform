"""A target that replays a fixed script instead of running an agent."""

from __future__ import annotations

from eval_platform.types import Case, Step, Trajectory


class ScriptedTarget:
    """Replays the case's own script. Free, deterministic, and the target the
    gate and report tests use so they never depend on the agent platform."""

    name = "scripted"
    capabilities = frozenset({"agent", "scripted"})

    def run(self, case: Case) -> Trajectory:
        """Turn `case.script` into a `Trajectory`, step for step.

        Each script item is a dict with keys `kind` and `name` (required)
        and optional `input`, `output`, `latency_ms`, `tokens_in`,
        `tokens_out`, `cost_usd`, and `error`, mapped straight onto `Step`.
        The trailing item may also carry `status`, `answer`, and
        `side_effects` for the resulting trajectory; unset, `status`
        defaults to "completed" and `answer` and `side_effects` default to
        `None` and empty. `cost_usd` and `wall_ms` on the trajectory are the
        sums of the per-step values.

        Raises `ValueError` if `case.script` is empty or `None`: this
        target has nothing to replay.
        """
        if not case.script:
            raise ValueError(f"case {case.name} has no script for the scripted target")
        steps: list[Step] = []
        status, answer, side_effects = "completed", None, []
        for item in case.script:
            steps.append(
                Step(
                    kind=item["kind"],
                    name=item["name"],
                    input=item.get("input"),
                    output=item.get("output"),
                    latency_ms=float(item.get("latency_ms", 0.0)),
                    tokens_in=int(item.get("tokens_in", 0)),
                    tokens_out=int(item.get("tokens_out", 0)),
                    cost_usd=float(item.get("cost_usd", 0.0)),
                    error=item.get("error"),
                )
            )
            status = item.get("status", status)
            answer = item.get("answer", answer)
            side_effects = item.get("side_effects", side_effects)
        return Trajectory(
            target=self.name,
            goal=case.goal,
            steps=tuple(steps),
            status=status,
            answer=answer,
            side_effects=tuple(side_effects),
            cost_usd=sum(s.cost_usd for s in steps),
            wall_ms=sum(s.latency_ms for s in steps),
            meta={"scripted": True},
        )
