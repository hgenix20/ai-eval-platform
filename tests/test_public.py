from datetime import date
from pathlib import Path

import pytest
from inspect_ai import Task
from inspect_ai import eval as inspect_eval
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.model import ModelOutput
from inspect_ai.scorer import match
from pydantic import HttpUrl

from eval_platform.budget import Budget
from eval_platform.catalog import CatalogEntry
from eval_platform.catalog.schema import License, LicenseStatus, Runner, RunnerKind
from eval_platform.suites import eval_log_to_suite_result, run_public


def _tiny_task() -> Task:
    return Task(
        dataset=MemoryDataset([Sample(input="2+2?", target="4"), Sample(input="3+3?", target="6")]),
        scorer=match(),
    )


def test_eval_log_converts_to_suite_result(tmp_path: Path):
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
    r = eval_log_to_suite_result(log, suite="public_tiny", target="mockllm/model")
    assert r.metrics["accuracy"] == pytest.approx(0.5)
    assert r.metrics["samples_total"] == 2 and len(r.cases) == 2
    assert [c.passed for c in r.cases] == [True, False]
    assert r.meta["task"] and r.meta["status"] == "success"


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
