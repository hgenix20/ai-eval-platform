from datetime import date
from pathlib import Path

import pytest
from inspect_ai import Task
from inspect_ai import eval as inspect_eval
from inspect_ai._util.error import PrerequisiteError
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.log import EvalError, EvalLog
from inspect_ai.model import ModelOutput
from inspect_ai.scorer import match
from pydantic import HttpUrl

import eval_platform.suites.public as public_mod
from eval_platform.budget import Budget, BudgetExceeded
from eval_platform.catalog import CatalogEntry
from eval_platform.catalog.schema import License, LicenseStatus, Runner, RunnerKind
from eval_platform.suites import eval_log_to_suite_result, run_public


def _tiny_task() -> Task:
    return Task(
        dataset=MemoryDataset([Sample(input="2+2?", target="4"), Sample(input="3+3?", target="6")]),
        scorer=match(),
    )


def _tiny_log(tmp_path: Path) -> EvalLog:
    """Run the tiny two-sample task once for real, through mockllm, and
    return the resulting EvalLog: one correct answer, one wrong answer."""
    outputs = [
        ModelOutput.from_content(model="mockllm", content="4"),
        ModelOutput.from_content(model="mockllm", content="7"),
    ]
    [log] = inspect_eval(
        _tiny_task(),
        model="mockllm/model",
        model_args={"custom_outputs": outputs},
        log_dir=str(tmp_path),
        display="none",
    )
    return log


def test_eval_log_converts_to_suite_result(tmp_path: Path):
    log = _tiny_log(tmp_path)
    r = eval_log_to_suite_result(log, suite="public_tiny", target="mockllm/model")
    assert r.metrics["accuracy"] == pytest.approx(0.5)
    assert r.metrics["samples_total"] == 2 and len(r.cases) == 2
    assert [c.passed for c in r.cases] == [True, False]
    assert r.metrics["samples_unscored"] == 0.0
    assert r.meta["task"] and r.meta["status"] == "success"


def test_eval_log_skips_unscored_samples(tmp_path: Path):
    """A NaN score (Inspect's unscored sentinel) is skipped, not a fail."""
    log = _tiny_log(tmp_path)
    assert log.samples is not None
    scores = log.samples[1].scores
    assert scores is not None
    scores["match"].value = float("nan")
    r = eval_log_to_suite_result(log, suite="public_tiny", target="mockllm/model")
    assert r.cases[1].skipped_reason == "unscored"
    assert r.cases[1].passed is False
    assert r.cases[1].grades == ()
    assert r.metrics["samples_unscored"] == 1.0
    assert set(r.metrics) == {
        "accuracy",
        "samples_total",
        "samples_completed",
        "input_tokens",
        "output_tokens",
        "usd",
        "samples_unscored",
        "samples_errored",
        "match.accuracy",
        "match.stderr",
    }


def test_eval_log_records_error_status_and_sample_errors(tmp_path: Path):
    """An Inspect run stopped by a provider error (status != "success")
    must not be read as a measurement: the failing sample is skipped with
    its error message, `samples_errored` counts it, and `meta["error"]`
    carries the run-level error text."""
    log = _tiny_log(tmp_path)
    log.status = "error"
    log.error = EvalError(
        message="Error code: 402 - credits depleted", traceback="", traceback_ansi=""
    )
    assert log.samples is not None
    log.samples[0].error = EvalError(
        message="sample 402: credits depleted", traceback="", traceback_ansi=""
    )
    r = eval_log_to_suite_result(log, suite="public_ifeval", target="mockllm/model")
    assert r.meta["status"] == "error"
    assert r.meta["error"] == "Error code: 402 - credits depleted"
    assert r.metrics["samples_errored"] == 1.0
    assert r.cases[0].passed is False
    assert r.cases[0].grades == ()
    assert r.cases[0].skipped_reason == "error: sample 402: credits depleted"
    # The other sample carries no error and is scored normally.
    assert r.cases[1].skipped_reason is None


def test_eval_log_truncates_long_error_messages_in_skipped_reason(tmp_path: Path):
    """A sample error message longer than 120 characters is truncated in
    `skipped_reason`, so one runaway provider message cannot blow up the
    report."""
    log = _tiny_log(tmp_path)
    assert log.samples is not None
    long_message = "x" * 500
    log.samples[0].error = EvalError(message=long_message, traceback="", traceback_ansi="")
    r = eval_log_to_suite_result(log, suite="public_ifeval", target="mockllm/model")
    assert r.cases[0].skipped_reason == f"error: {long_message[:120]}"


def test_eval_log_meta_error_falls_back_to_status_with_no_log_error(tmp_path: Path):
    """When Inspect sets a non-success status but leaves `log.error` unset
    (e.g. "cancelled"), `meta["error"]` falls back to the status string
    rather than being absent."""
    log = _tiny_log(tmp_path)
    log.status = "cancelled"
    log.error = None
    r = eval_log_to_suite_result(log, suite="public_ifeval", target="mockllm/model")
    assert r.meta["error"] == "cancelled"


def test_eval_log_samples_errored_is_zero_with_no_errors(tmp_path: Path):
    log = _tiny_log(tmp_path)
    r = eval_log_to_suite_result(log, suite="public_ifeval", target="mockllm/model")
    assert r.metrics["samples_errored"] == 0.0
    assert "error" not in r.meta


def test_eval_log_copies_every_scorer_metric(tmp_path: Path):
    """Every scorer's metrics land in `metrics` as `f"{score.name}.{metric_name}"`,
    on top of the headline `accuracy` (which stays the first scorer's
    accuracy/mean, unaffected by this)."""
    log = _tiny_log(tmp_path)
    r = eval_log_to_suite_result(log, suite="public_tiny", target="mockllm/model")
    assert r.metrics["match.accuracy"] == pytest.approx(0.5)
    assert r.metrics["match.stderr"] == pytest.approx(0.5)
    assert r.metrics["accuracy"] == pytest.approx(0.5)


def _entry(
    kind: RunnerKind = "inspect_evals",
    ref: str = "inspect_evals/ifeval",
    lic: LicenseStatus = "verified",
) -> CatalogEntry:
    return CatalogEntry(
        id="ifeval",
        name="IFEval",
        url=HttpUrl("https://example.org/ifeval"),
        category="capability",
        maintainer="g",
        size="541",
        license=License(code="Apache-2.0", data="Apache-2.0", status=lic),
        scoring="exact-match",
        runner=Runner(kind=kind, ref=ref),
        status="current",
        cost_class="low",
        verified=date(2026, 9, 7),
        sources=[HttpUrl("https://example.org/ifeval")],
    )


def test_run_public_refuses_non_runnable(tmp_path: Path):
    with pytest.raises(ValueError, match="not runnable"):
        run_public(
            _entry(lic="non-commercial"),
            model="mockllm/model",
            limit=1,
            budget=Budget(1, 60),
            log_dir=tmp_path,
        )
    with pytest.raises(ValueError, match="not runnable"):
        run_public(
            _entry(kind="external", ref="x"),
            model="mockllm/model",
            limit=1,
            budget=Budget(1, 60),
            log_dir=tmp_path,
        )


def test_run_public_divides_cost_limit_by_sample_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Inspect's cost_limit caps spend per sample, not per run: with a
    4-sample limit and $1.00 remaining, each sample may spend up to $0.25."""
    log = _tiny_log(tmp_path)
    calls: list[dict] = []

    def fake_eval(*args: object, **kwargs: object) -> list[EvalLog]:
        calls.append(kwargs)
        return [log]

    monkeypatch.setattr(public_mod, "inspect_eval", fake_eval)
    budget = Budget(max_usd=1.0, max_wall_s=60)
    result = run_public(
        _entry(), model="openai/gpt-4o-mini", limit=4, budget=budget, log_dir=tmp_path
    )
    assert calls[0]["cost_limit"] == pytest.approx(1.0 / 4)
    assert result.meta["cost_cap_mode"] == "per_sample_divided"


def test_run_public_caps_at_full_remaining_without_a_sample_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """With no sample limit there is no count to divide by, so the
    per-sample cap is the whole remaining budget."""
    log = _tiny_log(tmp_path)
    calls: list[dict] = []

    def fake_eval(*args: object, **kwargs: object) -> list[EvalLog]:
        calls.append(kwargs)
        return [log]

    monkeypatch.setattr(public_mod, "inspect_eval", fake_eval)
    budget = Budget(max_usd=1.0, max_wall_s=60)
    result = run_public(
        _entry(), model="openai/gpt-4o-mini", limit=None, budget=budget, log_dir=tmp_path
    )
    assert calls[0]["cost_limit"] == pytest.approx(1.0)
    assert result.meta["cost_cap_mode"] == "per_sample_uncapped_count"


def test_run_public_passes_no_cost_arguments_for_mock_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A mockllm model spends nothing and is absent from Inspect's model
    registry, so it gets neither a cost cap nor a cost table."""
    log = _tiny_log(tmp_path)
    calls: list[dict] = []

    def fake_eval(*args: object, **kwargs: object) -> list[EvalLog]:
        calls.append(kwargs)
        return [log]

    monkeypatch.setattr(public_mod, "inspect_eval", fake_eval)
    budget = Budget(max_usd=1.0, max_wall_s=60)
    result = run_public(_entry(), model="mockllm/model", limit=4, budget=budget, log_dir=tmp_path)
    assert calls[0].get("cost_limit") is None
    assert calls[0].get("model_cost_config") is None
    assert result.meta["cost_cap_mode"] == "none_free_model"
    assert "zero_cost_model" not in result.meta


def test_run_public_wraps_missing_cost_data_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """PrerequisiteError about missing cost data (e.g. a model this
    function did not anticipate as free) becomes a plain ValueError naming
    the model, not the raw Inspect internal error."""

    def fake_eval(*args: object, **kwargs: object) -> list[EvalLog]:
        raise PrerequisiteError(
            "cost_limit requires cost data for all models. Missing cost data for: "
            "openai/gpt-4o-mini. Use set_model_cost() or --model-cost-config to configure pricing."
        )

    monkeypatch.setattr(public_mod, "inspect_eval", fake_eval)
    budget = Budget(max_usd=1.0, max_wall_s=60)
    with pytest.raises(ValueError, match="no cost data"):
        run_public(_entry(), model="openai/gpt-4o-mini", limit=4, budget=budget, log_dir=tmp_path)


def test_run_public_refuses_when_budget_exhausted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """remaining_usd() <= 0 must raise before inspect_eval is called at all,
    not be passed through as a None cost_limit (which would mean no cap)."""
    log = _tiny_log(tmp_path)
    calls: list[dict] = []

    def fake_eval(*args: object, **kwargs: object) -> list[EvalLog]:
        calls.append(kwargs)
        return [log]

    monkeypatch.setattr(public_mod, "inspect_eval", fake_eval)
    budget = Budget(max_usd=1.0, max_wall_s=60, spent_usd=1.0)
    with pytest.raises(BudgetExceeded, match="no budget remaining"):
        run_public(_entry(), model="mockllm/model", limit=4, budget=budget, log_dir=tmp_path)
    assert calls == []


def test_run_public_no_cost_cap_passes_no_cost_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """no_cost_cap=True skips both cost_limit and model_cost_config, no
    matter what the model is, and records the mode that says the external
    provider's credits are the real spend cap."""
    log = _tiny_log(tmp_path)
    calls: list[dict] = []

    def fake_eval(*args: object, **kwargs: object) -> list[EvalLog]:
        calls.append(kwargs)
        return [log]

    monkeypatch.setattr(public_mod, "inspect_eval", fake_eval)
    budget = Budget(max_usd=1.0, max_wall_s=60)
    result = run_public(
        _entry(),
        model="hf-inference-providers/meta-llama/Llama-3.1-8B-Instruct:deepinfra",
        limit=5,
        budget=budget,
        log_dir=tmp_path,
        no_cost_cap=True,
    )
    assert calls[0].get("cost_limit") is None
    assert calls[0].get("model_cost_config") is None
    assert result.meta["cost_cap_mode"] == "none_external_budget"


def test_run_public_no_cost_cap_without_limit_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """no_cost_cap with no sample limit and no full=True would run an
    unbounded, uncapped benchmark; this is refused before inspect_eval is
    called at all."""

    def fake_eval(*args: object, **kwargs: object) -> list[EvalLog]:
        raise AssertionError("inspect_eval must not be called")

    monkeypatch.setattr(public_mod, "inspect_eval", fake_eval)
    budget = Budget(max_usd=1.0, max_wall_s=60)
    with pytest.raises(ValueError, match="no_cost_cap requires a sample limit"):
        run_public(
            _entry(),
            model="hf-inference-providers/x:deepinfra",
            limit=None,
            budget=budget,
            log_dir=tmp_path,
            no_cost_cap=True,
        )


def test_run_public_no_cost_cap_full_allows_no_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """full=True is the explicit escape valve for an intentional unlimited
    run: no ValueError, limit=None reaches inspect_eval, and the result
    records both that it ran the full dataset and how the cost cap was
    handled."""
    log = _tiny_log(tmp_path)
    calls: list[dict] = []

    def fake_eval(*args: object, **kwargs: object) -> list[EvalLog]:
        calls.append(kwargs)
        return [log]

    monkeypatch.setattr(public_mod, "inspect_eval", fake_eval)
    budget = Budget(max_usd=1.0, max_wall_s=60)
    result = run_public(
        _entry(),
        model="hf-inference-providers/x:deepinfra",
        limit=None,
        budget=budget,
        log_dir=tmp_path,
        no_cost_cap=True,
        full=True,
    )
    assert calls[0]["limit"] is None
    assert result.meta["full_run"] is True
    assert result.meta["cost_cap_mode"] == "none_external_budget"


def test_run_public_forwards_generate_kwargs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A `generate` dict is forwarded to inspect_eval as keyword arguments
    and recorded verbatim in the result's meta for later comparison."""
    log = _tiny_log(tmp_path)
    calls: list[dict] = []

    def fake_eval(*args: object, **kwargs: object) -> list[EvalLog]:
        calls.append(kwargs)
        return [log]

    monkeypatch.setattr(public_mod, "inspect_eval", fake_eval)
    budget = Budget(max_usd=1.0, max_wall_s=60)
    generate = {
        "temperature": 0.0,
        "max_tokens": 1024,
        "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
    }
    result = run_public(
        _entry(),
        model="mockllm/model",
        limit=2,
        budget=budget,
        log_dir=tmp_path,
        generate=generate,
    )
    assert calls[0]["temperature"] == 0.0
    assert calls[0]["max_tokens"] == 1024
    assert calls[0]["extra_body"] == generate["extra_body"]
    assert result.meta["generate"] == generate


@pytest.mark.network
def test_run_public_ifeval_two_samples_with_mock_model(tmp_path: Path):
    r = run_public(
        _entry(),
        model="mockllm/model",
        limit=2,
        budget=Budget(max_usd=1.0, max_wall_s=300),
        log_dir=tmp_path,
    )
    assert r.metrics["samples_total"] == 2 and r.suite == "public_ifeval"
