"""Decide whether a set of suite results may merge. Absolute thresholds apply
always; relative ones need a baseline and are reported not_measured without
one. A single fail or unstable verdict blocks.

A baseline and a current summary can each carry a `target` (the model or
target name the run measured). When both are present and differ, the
relative comparison is meaningless, since it would be measuring a model
change rather than a regression; see `compare` for how that case is
handled."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .config import GateConfig, Threshold

Verdict = Literal["pass", "fail", "unstable", "not_measured"]


@dataclass(frozen=True)
class MetricVerdict:
    """The gate's judgment on one suite's threshold metric: what it compared,
    what it found, and why."""

    suite: str
    metric: str
    baseline: float | None
    current: float | None
    threshold: str
    verdict: Verdict
    detail: str


@dataclass(frozen=True)
class GateReport:
    """The full set of per-suite verdicts from one gate run."""

    verdicts: tuple[MetricVerdict, ...]

    @property
    def passed(self) -> bool:
        """True when no verdict is "fail" or "unstable". A "not_measured"
        verdict does not block: a suite that did not run is not a
        regression, just missing evidence."""
        return all(v.verdict not in ("fail", "unstable") for v in self.verdicts)


def _describe(t: Threshold) -> str:
    """Render a Threshold's non-None bounds as a short human-readable string,
    for display in reports (e.g. "min=1.0, max_drop=0.02")."""
    parts = [f"{k}={v}" for k, v in t.model_dump(exclude={"metric"}).items() if v is not None]
    return ", ".join(parts) or "none"


def _metric(summary: dict[str, Any] | None, suite: str, name: str) -> float | None:
    """Pull one named metric out of a summary dict's "metrics" mapping.
    Returns None if the summary is missing, or the metric is absent.

    Raises ValueError if the metric is present but cannot be read as a
    float (for example a string), naming the suite and metric so the
    caller can find the bad value.
    """
    if not summary:
        return None
    value = summary.get("metrics", {}).get(name)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"{suite}.{name}: metric value {value!r} is not numeric") from e


def _relative_failures(t: Threshold, base: float, cur: float) -> tuple[list[str], str | None]:
    """Check `cur` against `base` under `t`'s relative bounds (max_drop,
    max_rise, max_increase_pct). Returns the list of failure messages (empty
    if none) and, separately, a not_measured detail for the one case a
    failure list cannot express: max_increase_pct against a zero baseline,
    which is mathematically undefined for any positive current value.
    """
    failures: list[str] = []
    undefined_pct_detail: str | None = None
    if t.max_drop is not None and cur < base - t.max_drop:
        failures.append(f"dropped {base - cur:.4f} > max_drop {t.max_drop}")
    if t.max_rise is not None and cur > base + t.max_rise:
        failures.append(f"rose {cur - base:.4f} > max_rise {t.max_rise}")
    if t.max_increase_pct is not None:
        if base > 0:
            if cur > base * (1 + t.max_increase_pct / 100):
                failures.append(
                    f"+{(cur / base - 1) * 100:.1f}% > max_increase_pct {t.max_increase_pct}"
                )
        elif cur > 0:
            undefined_pct_detail = "baseline is zero; percentage increase undefined"
        # base == 0 and cur == 0: no change from a zero baseline; this
        # check passes.
    return failures, undefined_pct_detail


def _judge(
    t: Threshold, base: float | None, cur: float, *, target_mismatch: str | None = None
) -> tuple[Verdict, str]:
    """Apply one threshold's checks to a current value, given an optional
    baseline. Absolute checks (min/max) always apply, baseline or not, and
    are evaluated first: a failed absolute check fails the verdict outright,
    before anything relative is considered. With no baseline: if the
    threshold has an absolute bound, the verdict rests on that bound alone
    (pass or fail); if the threshold has only relative bounds, the verdict
    is not_measured, since nothing about it could be evaluated.

    `target_mismatch`, when not None, is a detail string set by the caller
    because the baseline and current summary were measured on different
    targets. Once the absolute checks have passed, a set `target_mismatch`
    short-circuits straight to a not_measured verdict carrying that detail:
    a relative comparison (max_drop, max_rise, max_increase_pct) between two
    different targets would be measuring a model change, not a regression,
    so it is skipped rather than evaluated.

    max_increase_pct against a zero baseline is a special case: a percentage
    increase from zero is mathematically undefined. If the current value is
    also zero (no change), the check passes; if the current value is above
    zero, the check cannot be evaluated and contributes not_measured, unless
    an absolute check already failed, in which case the failure wins.
    """
    has_absolute = t.min is not None or t.max is not None
    has_relative = (
        t.max_drop is not None or t.max_rise is not None or t.max_increase_pct is not None
    )

    absolute_failures: list[str] = []
    if t.min is not None and cur < t.min:
        absolute_failures.append(f"{cur:.4f} < min {t.min}")
    if t.max is not None and cur > t.max:
        absolute_failures.append(f"{cur:.4f} > max {t.max}")
    if absolute_failures:
        return "fail", "; ".join(absolute_failures)

    if target_mismatch is not None:
        return "not_measured", target_mismatch

    failures: list[str] = []
    undefined_pct_detail: str | None = None
    if base is not None and has_relative:
        failures, undefined_pct_detail = _relative_failures(t, base, cur)
    if failures:
        return "fail", "; ".join(failures)
    if undefined_pct_detail is not None:
        return "not_measured", undefined_pct_detail
    if base is None and has_relative and not has_absolute:
        return "not_measured", "no baseline for relative check"
    return "pass", "within thresholds"


def _target_mismatch(
    base_summary: dict[str, Any] | None, cur_summary: dict[str, Any] | None
) -> str | None:
    """Detail string for a target mismatch between `base_summary` and
    `cur_summary`, or None when the check does not apply.

    Applies only when both summaries are present and both carry a
    non-None top-level `target` and those targets differ; a baseline
    with no `target` key (written before this field existed) or a
    current summary missing one never triggers this check.
    """
    if base_summary is None or cur_summary is None:
        return None
    baseline_target = base_summary.get("target")
    current_target = cur_summary.get("target")
    if baseline_target is None or current_target is None:
        return None
    if baseline_target == current_target:
        return None
    return f"target differs from baseline ({baseline_target} vs {current_target})"


def compare(
    config: GateConfig,
    baseline: dict[str, dict[str, Any]],
    current: dict[str, dict[str, Any]],
) -> GateReport:
    """Compare `current` suite summaries against `config`'s thresholds, using
    `baseline` for any relative checks.

    `baseline` and `current` map suite name to a summary dict shaped like
    `{"metrics": {...}}` (a SuiteResult.to_dict(), or just its metrics
    wrapper). A suite present in `config.suites` but absent from `current`
    yields a not_measured verdict with detail "suite not run"; a suite that
    is present but whose summary lacks the threshold metric yields
    not_measured with detail "metric absent from summary". Neither raises:
    an unrun suite, or one missing this particular metric, is not a gate
    failure by itself.

    A current summary carrying `meta["status"]` set to anything other than
    "success" (an errored or cancelled Inspect run, see
    `eval_log_to_suite_result`) is likewise treated as not measured, with
    detail "latest run errored", regardless of what its metric value
    happens to be. This is a defensive check: `write_summary(...,
    promote_latest=False)` already keeps an errored run out of
    `latest.json` in the normal flow, but a summary carrying an error
    status must never be read as a pass or a fail if one reaches this
    function some other way (a stale file, a hand-copied summary).

    When both the baseline and the current summary carry a top-level
    `target` field and the two differ, the run was measured against a
    different model than the baseline was: a relative check (max_drop,
    max_rise, max_increase_pct) between them would be reporting a model
    change as a regression. Absolute checks (min/max) still apply in that
    case, since a suite may carry a floor or ceiling that has to hold
    regardless of target; if an absolute check fails, the verdict is
    fail. Otherwise the verdict is not_measured, with detail
    `f"target differs from baseline ({baseline_target} vs
    {current_target})"`. A baseline file written before this field
    existed has no `target` key and is unaffected: the check only fires
    when both sides state a target and they disagree.

    Failure mode: raises ValueError if a metric value in `baseline` or
    `current` is present but not numeric (see `_metric`).
    """
    out: list[MetricVerdict] = []
    for suite, t in config.suites.items():
        base_summary = baseline.get(suite)
        cur_summary = current.get(suite)
        base = _metric(base_summary, suite, t.metric)
        cur_status = (cur_summary or {}).get("meta", {}).get("status")
        if cur_status is not None and cur_status != "success":
            out.append(
                MetricVerdict(
                    suite, t.metric, base, None, _describe(t), "not_measured", "latest run errored"
                )
            )
            continue
        cur = _metric(cur_summary, suite, t.metric)
        if cur is None:
            detail = "suite not run" if cur_summary is None else "metric absent from summary"
            out.append(
                MetricVerdict(suite, t.metric, base, None, _describe(t), "not_measured", detail)
            )
            continue
        target_mismatch = _target_mismatch(base_summary, cur_summary)
        verdict, detail = _judge(t, base, cur, target_mismatch=target_mismatch)
        out.append(MetricVerdict(suite, t.metric, base, cur, _describe(t), verdict, detail))
    return GateReport(tuple(out))
