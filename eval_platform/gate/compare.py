"""Decide whether a set of suite results may merge. Absolute thresholds apply
always; relative ones need a baseline and are reported not_measured without
one. A single fail or unstable verdict blocks."""

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


def _metric(summary: dict[str, Any] | None, name: str) -> float | None:
    """Pull one named metric out of a summary dict's "metrics" mapping.
    Returns None if the summary is missing, or the metric is absent."""
    if not summary:
        return None
    value = summary.get("metrics", {}).get(name)
    return float(value) if value is not None else None


def _judge(t: Threshold, base: float | None, cur: float) -> tuple[Verdict, str]:
    """Apply one threshold's checks to a current value, given an optional
    baseline. Absolute checks (min/max) always apply, baseline or not.
    Relative checks (max_drop/max_rise/max_increase_pct) apply only when a
    baseline is present. With no baseline: if the threshold has an absolute
    bound, the verdict rests on that bound alone (pass or fail); if the
    threshold has only relative bounds, the verdict is not_measured, since
    nothing about it could be evaluated.
    """
    failures: list[str] = []
    has_absolute = t.min is not None or t.max is not None
    has_relative = (
        t.max_drop is not None or t.max_rise is not None or t.max_increase_pct is not None
    )
    if t.min is not None and cur < t.min:
        failures.append(f"{cur:.4f} < min {t.min}")
    if t.max is not None and cur > t.max:
        failures.append(f"{cur:.4f} > max {t.max}")
    if base is not None and has_relative:
        if t.max_drop is not None and cur < base - t.max_drop:
            failures.append(f"dropped {base - cur:.4f} > max_drop {t.max_drop}")
        if t.max_rise is not None and cur > base + t.max_rise:
            failures.append(f"rose {cur - base:.4f} > max_rise {t.max_rise}")
        if (
            t.max_increase_pct is not None
            and base > 0
            and cur > base * (1 + t.max_increase_pct / 100)
        ):
            failures.append(
                f"+{(cur / base - 1) * 100:.1f}% > max_increase_pct {t.max_increase_pct}"
            )
    if failures:
        return "fail", "; ".join(failures)
    if base is None and has_relative and not has_absolute:
        return "not_measured", "no baseline for relative check"
    return "pass", "within thresholds"


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
    (or whose threshold metric is missing) yields a not_measured verdict
    rather than raising: an unrun suite is not a gate failure by itself.
    """
    out: list[MetricVerdict] = []
    for suite, t in config.suites.items():
        base = _metric(baseline.get(suite), t.metric)
        cur = _metric(current.get(suite), t.metric)
        if cur is None:
            out.append(
                MetricVerdict(
                    suite, t.metric, base, None, _describe(t), "not_measured", "suite not run"
                )
            )
            continue
        verdict, detail = _judge(t, base, cur)
        out.append(MetricVerdict(suite, t.metric, base, cur, _describe(t), verdict, detail))
    return GateReport(tuple(out))
