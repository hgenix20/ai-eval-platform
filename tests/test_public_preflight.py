"""The requirement preflight and the two new run options of the public
runner: what blocks a run before Inspect loads anything, what only warns,
and how the grader role and epochs reach `inspect_eval`."""

from datetime import date
from pathlib import Path

import pytest
from inspect_ai._util.error import PrerequisiteError
from inspect_ai.log import EvalLog
from pydantic import HttpUrl

import eval_platform.suites.public as public_mod
from eval_platform.budget import Budget
from eval_platform.catalog import CatalogEntry, load_catalog
from eval_platform.catalog.schema import License, Runner
from eval_platform.suites.public import (
    KNOWN_REQUIREMENTS,
    docker_engine_reachable,
    preflight,
    prerequisite_message,
    run_public,
)

ROOT = Path(__file__).resolve().parents[1]


def _entry(requires: list[str]) -> CatalogEntry:
    return CatalogEntry(
        id="probe",
        name="Probe",
        url=HttpUrl("https://example.com/probe"),
        category="capability",
        maintainer="tests",
        size="2",
        license=License(code="MIT", data="MIT", status="verified"),
        scoring="exact-match",
        runner=Runner(kind="inspect_evals", ref="inspect_evals/ifeval"),
        status="current",
        cost_class="low",
        requires=requires,
        verified=date(2026, 9, 15),
        sources=[HttpUrl("https://example.com/probe")],
    )


def test_preflight_passes_with_nothing_required():
    assert preflight(_entry([]), grader_model=None, env={}) == ([], [])


def test_preflight_blocks_docker_when_engine_is_down():
    blocking, advisory = preflight(
        _entry(["docker"]), grader_model=None, env={}, docker_check=lambda: False
    )
    assert len(blocking) == 1 and blocking[0].startswith("docker:")
    assert advisory == []


def test_preflight_passes_docker_when_engine_is_up():
    assert preflight(_entry(["docker"]), grader_model=None, env={}, docker_check=lambda: True) == (
        [],
        [],
    )


def test_preflight_blocks_judge_without_grader_model():
    blocking, _ = preflight(_entry(["api:judge"]), grader_model=None, env={})
    assert blocking and "--grader-model" in blocking[0]
    assert preflight(_entry(["api:judge"]), grader_model="mockllm/model", env={}) == ([], [])


def test_preflight_blocks_gated_dataset_without_token():
    blocking, _ = preflight(_entry(["hf-gated"]), grader_model=None, env={})
    assert blocking and blocking[0].startswith("hf-gated:")
    assert preflight(_entry(["hf-gated"]), grader_model=None, env={"HF_TOKEN": "x"}) == ([], [])


def test_preflight_reports_advisory_tags_without_blocking():
    blocking, advisory = preflight(_entry(["gpu", "api:user-sim"]), grader_model=None, env={})
    assert blocking == []
    assert [a.startswith(("gpu:", "api:user-sim:")) for a in advisory] == [True, True]
    assert advisory[1].startswith("api:user-sim:")


def test_preflight_blocks_an_unknown_tag():
    blocking, _ = preflight(_entry(["quantum"]), grader_model=None, env={})
    assert blocking == ["quantum: unknown requirement tag in the catalog entry probe"]


def test_every_catalog_requirement_tag_is_known():
    """A tag the preflight cannot check is a catalog error; this pins the
    vocabulary so a new tag has to be added to the preflight first."""
    tags = {tag for e in load_catalog(ROOT / "catalog" / "entries") for tag in e.requires}
    assert tags <= KNOWN_REQUIREMENTS, tags - KNOWN_REQUIREMENTS


def test_docker_check_is_false_without_a_binary(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(public_mod.shutil, "which", lambda _name: None)
    assert docker_engine_reachable() is False


def test_prerequisite_message_strips_markup_and_prefix():
    exc = PrerequisiteError(
        "ERROR: Unable to initialise OpenAI client\n\nNo [bold][blue]OPENAI_API_KEY[/blue][/bold]"
    )
    assert prerequisite_message(exc) == ("Unable to initialise OpenAI client\n\nNo OPENAI_API_KEY")


def test_run_public_passes_grader_role_and_epochs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """`grader_model` becomes `model_roles={"grader": ...}` and `epochs`
    passes through; both are recorded in meta as given."""
    from tests.test_public import _tiny_log  # noqa: PLC0415

    log: EvalLog = _tiny_log(tmp_path)
    calls: list[dict] = []

    def fake_eval(*args: object, **kwargs: object) -> list[EvalLog]:
        calls.append(kwargs)
        return [log]

    monkeypatch.setattr(public_mod, "inspect_eval", fake_eval)
    result = run_public(
        _entry([]),
        model="mockllm/model",
        limit=2,
        budget=Budget(max_usd=1.0, max_wall_s=60),
        log_dir=tmp_path,
        grader_model="mockllm/grader",
        epochs=1,
    )
    assert calls[0]["model_roles"] == {"grader": "mockllm/grader"}
    assert calls[0]["epochs"] == 1
    assert result.meta["grader_model"] == "mockllm/grader" and result.meta["epochs"] == 1


def test_run_public_omits_grader_role_and_epochs_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from tests.test_public import _tiny_log  # noqa: PLC0415

    log: EvalLog = _tiny_log(tmp_path)
    calls: list[dict] = []

    def fake_eval(*args: object, **kwargs: object) -> list[EvalLog]:
        calls.append(kwargs)
        return [log]

    monkeypatch.setattr(public_mod, "inspect_eval", fake_eval)
    result = run_public(
        _entry([]),
        model="mockllm/model",
        limit=2,
        budget=Budget(max_usd=1.0, max_wall_s=60),
        log_dir=tmp_path,
    )
    assert "model_roles" not in calls[0] and "epochs" not in calls[0]
    assert result.meta["grader_model"] is None and result.meta["epochs"] is None
