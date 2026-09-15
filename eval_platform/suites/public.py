"""Public benchmarks run through Inspect AI. The platform does not
reimplement any benchmark: it hands the catalog entry's task to
inspect_ai.eval and converts the EvalLog into the same SuiteResult shape the
built suites produce, so the gate and report treat both alike."""

from __future__ import annotations

import math
import os
import re
import shutil
import subprocess  # nosec B404  # the one call below runs a fixed docker argv
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import inspect_ai
from inspect_ai import eval as inspect_eval
from inspect_ai._util.error import PrerequisiteError
from inspect_ai.log import EvalLog

from eval_platform.budget import Budget, BudgetExceeded
from eval_platform.catalog import CatalogEntry
from eval_platform.telemetry import set_attributes, span
from eval_platform.types import CaseResult, Grade, SuiteResult


def _passed(value: Any) -> bool:
    """A score value counts as a pass when it is match()'s "C", or a truthy
    numeric/boolean 1. Anything else (e.g. "I", 0, False, other scorer
    vocabularies) counts as a fail. Phase 1 keeps pass/fail binary: a
    partial-credit float (e.g. 0.5) or a dict-valued score (per-dimension
    breakdowns) flattens to fail here by design, not by omission."""
    return value in ("C", 1, 1.0, True)


def _unscored(scores: dict[str, Any]) -> bool:
    """True when a sample carries no scores at all, or any scorer left a
    NaN value (Inspect's unscored sentinel, e.g. a grader that could not
    parse a judge's reply). A NaN is never `== ` anything including itself,
    so `_passed` alone would mark it a fail with no indication why; this
    catches it explicitly so the sample is skipped instead of counted as a
    failure."""
    if not scores:
        return True
    return any(isinstance(sc.value, float) and math.isnan(sc.value) for sc in scores.values())


def _headline(log: EvalLog) -> float:
    """The suite's single headline number: the first scorer's "accuracy" or
    "mean" metric if present, else that scorer's first metric. Returns 0.0
    when the log has no results or no scores at all."""
    if log.results is None or not log.results.scores:
        return 0.0
    metrics = log.results.scores[0].metrics
    for name in ("accuracy", "mean"):
        if name in metrics:
            return float(metrics[name].value)
    first = next(iter(metrics.values()), None)
    return float(first.value) if first is not None else 0.0


def _wall_ms_total(started_at: str, completed_at: str) -> float:
    """Milliseconds between `started_at` and `completed_at`, both ISO 8601
    timestamps as Inspect writes them in `log.stats`. Returns 0.0 if either
    is the empty string (Inspect's sentinel for a run interrupted before
    that timestamp was set), rather than raising, since a public summary
    must still carry this key even for an incomplete run.
    """
    if not started_at or not completed_at:
        return 0.0
    delta = datetime.fromisoformat(completed_at) - datetime.fromisoformat(started_at)
    return delta.total_seconds() * 1000.0


def _usage(log: EvalLog) -> tuple[int, int, float]:
    """Sum input tokens, output tokens, and dollar cost across every model
    Inspect recorded usage for. `log.stats` is always present (Inspect
    default-constructs it), so an empty `model_usage` dict is the only
    degenerate case, and it sums to zeros."""
    usage = log.stats.model_usage
    tin = sum(u.input_tokens for u in usage.values())
    tout = sum(u.output_tokens for u in usage.values())
    usd = sum(float(u.total_cost or 0.0) for u in usage.values())
    return tin, tout, usd


def eval_log_to_suite_result(log: EvalLog, *, suite: str, target: str) -> SuiteResult:
    """Convert an Inspect EvalLog into this platform's SuiteResult shape.

    Contract: one CaseResult per EvalSample in `log.samples`, in order. A
    sample whose own `error` is set (the provider or scorer failed on that
    sample specifically) becomes a skipped case: `passed=False`,
    `grades=()`, `skipped_reason=f"error: {message[:120]}"`; it is never
    also counted as unscored. A sample with no error but no scores at all,
    or with a NaN score from any scorer (Inspect's unscored sentinel),
    becomes a skipped case with `skipped_reason="unscored"` instead.
    Otherwise, a case passes when every scorer's value on that sample
    counts as a pass (see `_passed`); grades carry one entry per scorer,
    named by the scorer's key in `sample.scores`. `metrics["accuracy"]` is
    the suite's headline number (see `_headline`); `metrics["samples_unscored"]`
    is the count of skipped-as-unscored cases; `metrics["samples_errored"]`
    is the count of samples that carried their own `error` (this key is
    always present, 0.0 when none); `usd` is 0.0 when Inspect recorded no
    cost. Missing `log.results` (an incomplete or errored run) degrades
    `samples_total`/`samples_completed` to the sample count from
    `log.samples` rather than raising. `metrics["wall_ms_total"]` is the
    run's wall-clock duration in milliseconds, `log.stats.completed_at`
    minus `log.stats.started_at` (0.0 if either is the empty string, e.g.
    a run interrupted before that timestamp was set).
    `metrics["ms_per_sample"]` is `wall_ms_total / max(samples_completed, 1)`,
    so it stays defined even for a run that completed zero samples.

    An errored Inspect run (`log.status != "success"`, e.g. a provider ran
    out of credits mid-run) is a record of what happened, not a completed
    measurement: this function still converts it rather than raising, but
    marks it so a caller can refuse to publish it as the current number.
    `meta["error"]` is set to `str(log.error.message)` when `log.error` is
    present, else to `log.status` itself (e.g. `"cancelled"`), whenever
    `log.status != "success"`; the key is absent from `meta` on a
    successful run.

    On top of those six-plus-two metrics, every scorer's own metric is
    copied in as `f"{score.name}.{metric_name}"` (e.g. `match.accuracy`,
    `match.stderr`), for each score in `log.results.scores`, so a Phase-4
    IFEval-style task with several named scorers (prompt/instruction level,
    strict/loose) publishes every one of them, not just the headline
    number. A metric whose value is not a plain number (e.g. a per-category
    breakdown dict) is skipped rather than raising, since this function
    reports what it can convert instead of rejecting the whole log over a
    metric shape it does not know how to flatten.
    """
    cases: list[CaseResult] = []
    for s in log.samples or []:
        if s.error is not None:
            message = str(s.error.message)
            cases.append(
                CaseResult(
                    name=str(s.id),
                    passed=False,
                    grades=(),
                    trajectory=None,
                    skipped_reason=f"error: {message[:120]}",
                )
            )
            continue
        scores = s.scores or {}
        if _unscored(scores):
            cases.append(
                CaseResult(
                    name=str(s.id),
                    passed=False,
                    grades=(),
                    trajectory=None,
                    skipped_reason="unscored",
                )
            )
            continue
        grades = tuple(
            Grade(
                dimension=name,
                value=1.0 if _passed(sc.value) else 0.0,
                passed=_passed(sc.value),
                explanation=str(sc.explanation or ""),
            )
            for name, sc in scores.items()
        )
        cases.append(
            CaseResult(
                name=str(s.id),
                passed=bool(grades) and all(g.passed for g in grades),
                grades=grades,
                trajectory=None,
            )
        )
    tin, tout, usd = _usage(log)
    samples_unscored = sum(1 for c in cases if c.skipped_reason == "unscored")
    samples_errored = sum(1 for s in log.samples or () if s.error is not None)
    samples_completed = float(log.results.completed_samples if log.results else len(cases))
    wall_ms_total = _wall_ms_total(log.stats.started_at, log.stats.completed_at)
    metrics: dict[str, float] = {
        "accuracy": _headline(log),
        "samples_total": float(log.results.total_samples if log.results else len(cases)),
        "samples_completed": samples_completed,
        "input_tokens": float(tin),
        "output_tokens": float(tout),
        "usd": usd,
        "samples_unscored": float(samples_unscored),
        "samples_errored": float(samples_errored),
        "wall_ms_total": wall_ms_total,
        "ms_per_sample": wall_ms_total / max(samples_completed, 1.0),
    }
    for score in log.results.scores if log.results else ():
        for metric_name, metric in score.metrics.items():
            value = metric.value
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                metrics[f"{score.name}.{metric_name}"] = float(value)
    meta: dict[str, Any] = {
        "inspect_version": inspect_ai.__version__,
        "task": log.eval.task,
        "model": log.eval.model,
        "log_location": log.location,
        "status": log.status,
    }
    if log.status != "success":
        meta["error"] = str(log.error.message) if log.error else log.status
    return SuiteResult(
        suite=suite,
        target=target,
        started_at=log.stats.started_at,
        finished_at=log.stats.completed_at,
        cases=tuple(cases),
        metrics=metrics,
        meta=meta,
    )


# Every value a catalog entry may list under `requires`, with what the
# preflight does about it. Blocking tags stop a run before Inspect loads
# anything; advisory tags only print a note, since they describe a resource
# the platform cannot check from here.
BLOCKING_REQUIREMENTS = ("docker", "api:judge", "hf-gated")
ADVISORY_REQUIREMENTS = {
    "gpu": "loads a model locally; needs the local extra and a GPU with room for it",
    "live-web": "reaches the live web during the run, so results move with the web",
    "api:user-sim": "drives a simulated user with a second model; Inspect's user role "
    "falls back to --model when no other is configured",
    "vm": "needs a virtual machine image the task builds or downloads",
}
KNOWN_REQUIREMENTS = frozenset(BLOCKING_REQUIREMENTS) | frozenset(ADVISORY_REQUIREMENTS)
_RICH_MARKUP = re.compile(r"\[/?[a-z ]+\]")


def docker_engine_reachable(timeout_s: float = 20.0) -> bool:
    """Whether `docker version` succeeds within `timeout_s`. False when the
    docker binary is absent, the engine is down, or the call times out.
    Never raises: this is a preflight, and its only job is a verdict."""
    binary = shutil.which("docker")
    if binary is None:
        return False
    try:
        # Fixed argv, no shell, no user input: the only variable is the
        # resolved path of the docker binary itself.
        done = subprocess.run(  # noqa: S603  # nosec B603
            [binary, "version", "--format", "json"],
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def preflight(
    entry: CatalogEntry,
    *,
    grader_model: str | None,
    env: Mapping[str, str] | None = None,
    docker_check: Callable[[], bool] = docker_engine_reachable,
) -> tuple[list[str], list[str]]:
    """Check an entry's `requires` list before anything is loaded.

    Returns `(blocking, advisory)`: `blocking` holds one message per
    requirement that is not met and would make the run fail (a Docker
    engine that is not reachable, a task that grades with a model but no
    `grader_model` was given, a gated dataset with no `HF_TOKEN` in `env`);
    `advisory` holds one note per requirement the platform cannot verify
    from here. A tag outside `KNOWN_REQUIREMENTS` is reported as blocking,
    because a requirement nobody can check is a catalog error, not a pass.
    `env` defaults to the process environment; `docker_check` is injectable
    so tests never spawn docker.
    """
    environment = os.environ if env is None else env
    blocking: list[str] = []
    advisory: list[str] = []
    for tag in entry.requires:
        if tag == "docker":
            if not docker_check():
                blocking.append(
                    "docker: the Docker engine is not reachable (`docker version` failed); "
                    "start Docker Desktop or the engine and retry"
                )
        elif tag == "api:judge":
            if not grader_model:
                blocking.append(
                    "api:judge: this task grades answers with a model; pass "
                    "--grader-model <inspect model id> (Inspect's grader role)"
                )
        elif tag == "hf-gated":
            if not environment.get("HF_TOKEN"):
                blocking.append(
                    "hf-gated: the dataset is gated on Hugging Face; set HF_TOKEN to a token "
                    "whose account has accepted the dataset's terms"
                )
        elif tag in ADVISORY_REQUIREMENTS:
            advisory.append(f"{tag}: {ADVISORY_REQUIREMENTS[tag]}")
        else:
            blocking.append(f"{tag}: unknown requirement tag in the catalog entry {entry.id}")
    return blocking, advisory


def prerequisite_message(exc: PrerequisiteError) -> str:
    """Inspect's PrerequisiteError text with its console markup removed and
    the leading "ERROR:" dropped, so it reads as one plain message."""
    text = _RICH_MARKUP.sub("", str(exc)).strip()
    return text.removeprefix("ERROR:").strip()


def run_public(
    entry: CatalogEntry,
    *,
    model: str,
    limit: int | None,
    budget: Budget,
    log_dir: Path,
    task_args: dict[str, Any] | None = None,
    no_cost_cap: bool = False,
    full: bool = False,
    generate: dict[str, Any] | None = None,
    model_args: dict[str, Any] | None = None,
    grader_model: str | None = None,
    epochs: int | None = None,
) -> SuiteResult:
    """Run one catalog entry's public benchmark through Inspect AI and
    return it as a SuiteResult named `public_<id with - as _>`.

    Contract: raises ValueError before running anything when `entry` is not
    runnable through Inspect, i.e. `entry.runnable` is False or the runner
    kind is not `"inspect_evals"` (covers `non-commercial` license status,
    `external`/`builtin`/`none` runner kinds, and a missing ref). Running
    the `ifeval` catalog entry needs the `ifeval` extra installed
    (`pip install -e ".[ifeval]"`), since `inspect_evals`'s IFEval task
    imports that dependency at task-construction time, not at import time.

    Inspect's `cost_limit` bounds spend PER SAMPLE, not for the run as a
    whole; `--limit`, the sample count, is what actually bounds total
    spend. So for a priced model, when `limit` is a positive int the
    per-sample cap is `budget.remaining_usd() / limit`
    (`meta["cost_cap_mode"]` records `"per_sample_divided"`); when `limit`
    is None (or not a positive int) there is no sample count to divide by,
    so the cap is the full remaining budget per sample and
    `meta["cost_cap_mode"]` records `"per_sample_uncapped_count"`. That
    still caps any one sample, but not the run's total, since Inspect does
    not expose a run-level ceiling.

    Raises BudgetExceeded("usd") immediately after `budget.check()` if the
    budget is already exhausted (`remaining_usd() <= 0`): passing a zero or
    negative remaining amount as `cost_limit` would otherwise be read by
    Inspect as `0.0`, and passing None (as an exhausted-budget sentinel)
    would remove the cap entirely, so this is checked explicitly rather
    than folded into the cost_limit expression. `budget.check()` itself
    raises BudgetExceeded("wall") if the wall-clock ceiling has already
    passed. Charges `budget` with the run's actual dollar cost after
    Inspect returns; that charge can itself raise BudgetExceeded("usd") if
    the run's actual cost pushes total spend over the ceiling.

    A model whose name starts with `"mockllm/"` is free by construction: it
    generates canned output without calling any provider, so it spends
    nothing and no cap applies. Such a run gets neither `cost_limit` nor
    `model_cost_config`, and `meta["cost_cap_mode"]` records
    `"none_free_model"`. Passing either one would fail: a non-None
    `cost_limit` makes Inspect require registered cost data for every model
    in the run, and `mockllm` has no entry in Inspect's model registry at
    all, so `model_cost_config` cannot supply that data either (Inspect's
    `set_model_cost` raises ValueError for a model it does not already
    know).

    If Inspect raises PrerequisiteError over missing cost data for a priced
    model, that is re-raised as ValueError naming the model, rather than the
    raw Inspect internal error; any other exception from `inspect_eval`
    propagates unchanged.

    `no_cost_cap=True` is for a model Inspect cannot price at all (e.g. a
    Hugging Face Inference Providers id like
    `hf-inference-providers/meta-llama/Llama-3.1-8B-Instruct:deepinfra`):
    neither `cost_limit` nor `model_cost_config` is passed to Inspect, and
    `meta["cost_cap_mode"]` records `"none_external_budget"`, since the real
    spend cap in that case is the provider's own account credits, not
    anything this function can enforce. Because that mode enforces no
    per-sample or per-run cost ceiling of its own, it raises
    `ValueError("no_cost_cap requires a sample limit; pass limit or
    full=True")` when `limit is None` and `full` is not also True, before
    calling `inspect_eval` at all; `full=True` is the explicit override for
    an intentional unlimited run, and sets `meta["full_run"] = True` on the
    result. `budget.check()` and the post-run `budget.charge(usd)` still
    run in this mode: `usd` will be 0.0 since Inspect has no cost data to
    report, which is expected, not an error.

    `generate` is an optional dict of Inspect generate-config keyword
    arguments (e.g. `temperature`, `max_tokens`, `extra_body`) forwarded to
    `inspect_eval(...)` as-is, and copied into `meta["generate"]` verbatim
    (including None when not given) so a report can show exactly what
    generation settings produced a given run's numbers.

    `model_args` is an optional dict of Inspect model constructor keyword
    arguments (e.g. `device`, `torch_dtype` for the `hf/` provider, which
    loads a Hugging Face model locally instead of calling a hosted API).
    `inspect_eval(...)` always receives `model_args=model_args or {}` (never
    None, which Inspect's `hf/` provider does not accept in place of an
    empty mapping), while `meta["model_args"]` records the argument exactly
    as given, including None when not given, so a report can show whether a
    run used a specific local-model configuration.

    `grader_model`, when given, is passed to Inspect as
    `model_roles={"grader": grader_model}`: every task whose scorer calls
    `get_model(role="grader")` (SimpleQA Verified, CyberSecEval 4's
    prompt-injection task, and the other `api:judge` entries) then grades
    with that model instead of its own default, which for several tasks is
    a hosted OpenAI model. `epochs`, when given, overrides the task's
    default repeat count (GPQA Diamond and CyberSecEval 4 run four epochs
    by default, so `limit` samples become four times as many generate
    calls); both are recorded in `meta["grader_model"]` and
    `meta["epochs"]` as given, including None. Neither is validated here:
    the CLI rejects an `epochs` below 1 before calling.

    This function runs no preflight; `preflight` is a separate step the
    CLI takes first, so tests can exercise the run path without docker or
    a token.

    The `inspect_eval` call and the log conversion run inside an
    "eval.public" span carrying `suite`, `model`, and `limit` (-1 when
    `limit` is None) attributes up front, with `eval.usd` and
    `eval.samples` set from the converted result's metrics once it exists.
    """
    if not entry.runnable or entry.runner.kind != "inspect_evals" or not entry.runner.ref:
        raise ValueError(
            f"catalog entry {entry.id} is not runnable through Inspect "
            f"(kind={entry.runner.kind}, license={entry.license.status})"
        )
    if no_cost_cap and limit is None and not full:
        raise ValueError("no_cost_cap requires a sample limit; pass limit or full=True")
    budget.check()
    remaining = budget.remaining_usd()
    if remaining <= 0:
        raise BudgetExceeded("usd", "no budget remaining for a public run")
    # A mockllm model spends nothing and has no entry in Inspect's model
    # registry, so neither a cost cap nor a cost table can be attached to
    # it; every other model gets a per-sample cap cut from the budget.
    # no_cost_cap takes priority over both: it means Inspect has no price
    # for the model at all, so the external provider's own credits are the
    # real cap, not anything computed here.
    cost_kwargs: dict[str, Any] = {}
    if no_cost_cap:
        cost_cap_mode = "none_external_budget"
    elif model.startswith("mockllm/"):
        cost_cap_mode = "none_free_model"
    elif limit is not None and limit > 0:
        cost_kwargs["cost_limit"] = remaining / limit
        cost_cap_mode = "per_sample_divided"
    else:
        cost_kwargs["cost_limit"] = remaining
        cost_cap_mode = "per_sample_uncapped_count"
    eval_kwargs: dict[str, Any] = {**cost_kwargs, **(generate or {})}
    if grader_model is not None:
        eval_kwargs["model_roles"] = {"grader": grader_model}
    if epochs is not None:
        eval_kwargs["epochs"] = epochs
    suite_name = f"public_{entry.id.replace('-', '_')}"
    with span(
        "eval.public", suite=suite_name, model=model, limit=limit if limit is not None else -1
    ) as s:
        try:
            [log] = inspect_eval(
                entry.runner.ref,
                model=model,
                limit=limit,
                log_dir=str(log_dir),
                display="none",
                task_args=task_args or {},
                model_args=model_args or {},
                **eval_kwargs,
            )
        except PrerequisiteError as exc:
            if "cost data" in str(exc):
                raise ValueError(
                    f"model {model} has no cost data in Inspect; cannot enforce a spend cap"
                ) from exc
            raise
        result = eval_log_to_suite_result(log, suite=suite_name, target=model)
        result.meta["cost_cap_mode"] = cost_cap_mode
        result.meta["generate"] = generate
        result.meta["model_args"] = model_args
        result.meta["grader_model"] = grader_model
        result.meta["epochs"] = epochs
        if full:
            result.meta["full_run"] = True
        set_attributes(
            s,
            **{"eval.usd": result.metrics["usd"], "eval.samples": result.metrics["samples_total"]},
        )
    budget.charge(result.metrics["usd"])
    return result
