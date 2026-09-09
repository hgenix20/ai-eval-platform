from datetime import date
from pathlib import Path

import pytest
from inspect_ai import Task
from inspect_ai import eval as inspect_eval
from inspect_ai._util.error import PrerequisiteError
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.log import EvalLog
from inspect_ai.model import ModelCost, ModelOutput
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
    }


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
    result = run_public(_entry(), model="mockllm/model", limit=4, budget=budget, log_dir=tmp_path)
    assert calls[0]["cost_limit"] == pytest.approx(1.0 / 4)
    assert result.meta["cost_cap_mode"] == "per_sample_divided"
    assert calls[0]["model_cost_config"] == {
        "mockllm/model": ModelCost(
            input=0.0, output=0.0, input_cache_write=0.0, input_cache_read=0.0
        )
    }
    assert result.meta["zero_cost_model"] is True


def test_run_public_gives_zero_cost_only_to_mockllm_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A non-mockllm model gets no synthesized cost table: it presumably
    has real cost data of its own, so Inspect should check it normally."""
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
    assert calls[0]["model_cost_config"] is None
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
