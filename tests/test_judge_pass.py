import json
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import pytest
from inspect_ai.model import ModelOutput, get_model

from eval_platform.budget import Budget
from eval_platform.cli import main
from eval_platform.graders.base import GraderKind, Releasable
from eval_platform.graders.hhem import HHEMGrader
from eval_platform.graders.judge import RUBRICS, JudgeGrader
from eval_platform.graders.judge_cache import JudgeCache
from eval_platform.judge_pass import apply
from eval_platform.results import summary_to_result, write_summary
from eval_platform.suites.runner import run_suite
from eval_platform.targets.scripted import ScriptedTarget
from eval_platform.types import Case, Expect, Grade, compute_metrics


def _script():
    return [
        {"kind": "tool", "name": "search", "input": {}, "output": "Paris is in France."},
        # ScriptedTarget reads the trajectory's answer from the script's own
        # `answer` key, and a judge scores the answer: without this the
        # trajectory answers nothing and every verdict is unknown.
        {
            "kind": "model",
            "name": "final",
            "input": {},
            "output": "Paris is in France.",
            "answer": "Paris is in France.",
        },
    ]


def _cases():
    return [
        Case(
            name=f"c{n}",
            goal="q",
            target_requirements=["scripted"],
            script=_script(),
            expect=Expect(status="completed"),
        )
        for n in range(3)
    ]


class StubScorer:
    version = "stub"

    def score(self, pairs: Sequence[tuple[str, str]]) -> list[float]:
        return [0.9 for _ in pairs]


def _judge(tmp_path: Path, name: str, outputs: list[str]) -> JudgeGrader:
    # mockllm's custom_outputs must be ModelOutput instances, not raw text
    # (see tests/test_judge.py).
    scripted = [ModelOutput.from_content(model="mockllm", content=text) for text in outputs]
    return JudgeGrader(
        model=f"mockllm/{name}",
        rubric=RUBRICS["faithfulness"],
        cache=JudgeCache(tmp_path / name),
        model_handle=get_model("mockllm/model", custom_outputs=scripted),
    )


def _run():
    return run_suite("s", _cases(), ScriptedTarget(), budget=Budget(max_usd=1, max_wall_s=60))


def test_round_trip_summary(tmp_path: Path):
    result = _run()
    write_summary(result, tmp_path)
    back = summary_to_result(json.loads((tmp_path / "s" / "latest.json").read_text()))
    assert back.to_dict() == result.to_dict()


def test_apply_adds_grades_and_metrics(tmp_path: Path):
    result = _run()
    a = _judge(tmp_path, "a", ["VERDICT: SUPPORTED", "VERDICT: UNSUPPORTED", "nothing"])
    b = _judge(tmp_path, "b", ["VERDICT: SUPPORTED"] * 3)
    out = apply(
        result, {c.name: c for c in _cases()}, [a, b, HHEMGrader(scorer=StubScorer())], sample=None
    )
    dims = [g.dimension for g in out.cases[0].grades]
    assert dims == [
        "status",
        "judge:faithfulness:mockllm/a",
        "judge:faithfulness:mockllm/b",
        "unsupported_claims",
    ]
    m = out.metrics
    assert m["judge.faithfulness.mockllm/a.pass_rate"] == 0.5  # 1 pass, 1 fail, 1 unknown
    assert round(m["judge.faithfulness.mockllm/a.unknown_rate"], 4) == round(1 / 3, 4)
    assert m["judge.faithfulness.mockllm/b.pass_rate"] == 1.0
    assert m["judge.faithfulness.swap_agreement"] == 0.5  # over the 2 cases both labeled
    assert m["unsupported_rate"] == 0.0
    assert [c.passed for c in out.cases] == [True, False, True]  # unknown never fails a case
    assert out.meta["judge_pass"][-1]["graders"][0] == "faithfulness@1:mockllm/a"


def test_apply_replaces_same_dimension_and_respects_sample(tmp_path: Path):
    result = _run()
    a = _judge(tmp_path, "a", ["VERDICT: UNSUPPORTED"] * 3 + ["VERDICT: SUPPORTED"] * 3)
    once = apply(result, {c.name: c for c in _cases()}, [a], sample=2)
    assert sum(1 for c in once.cases for g in c.grades if g.dimension.startswith("judge:")) == 2
    twice = apply(once, {c.name: c for c in _cases()}, [a], sample=2)  # cache hits, same grades
    assert [g.dimension for g in twice.cases[0].grades].count("judge:faithfulness:mockllm/a") == 1


def test_apply_carries_forward_metrics_it_does_not_compute(tmp_path: Path):
    """A key `compute_metrics` never produces (a public benchmark's own
    score) survives a judge pass over that run."""
    result = replace(
        _run(), metrics={**_run().metrics, "instruction_following.prompt_strict_acc": 0.5}
    )
    out = apply(
        result,
        {c.name: c for c in _cases()},
        [_judge(tmp_path, "a", ["VERDICT: SUPPORTED"] * 3)],
        sample=None,
    )
    assert out.metrics["instruction_following.prompt_strict_acc"] == 0.5
    assert out.metrics["judge.faithfulness.mockllm/a.pass_rate"] == 1.0


def test_judge_pass_records_append_and_wrap_a_legacy_dict(tmp_path: Path):
    legacy = {"graders": ["old@1:mockllm/x"], "versions": {}, "at": "2026-01-01", "sample": None}
    result = replace(_run(), meta={"judge_pass": legacy})
    out = apply(
        result,
        {c.name: c for c in _cases()},
        [_judge(tmp_path, "a", ["VERDICT: SUPPORTED"] * 3)],
        sample=None,
    )
    records = out.meta["judge_pass"]
    assert [r["graders"] for r in records] == [["old@1:mockllm/x"], ["faithfulness@1:mockllm/a"]]
    again = apply(
        out,
        {c.name: c for c in _cases()},
        [_judge(tmp_path, "b", ["VERDICT: SUPPORTED"] * 3)],
        sample=1,
    )
    assert len(again.meta["judge_pass"]) == 3
    assert again.meta["judge_pass"][-1]["sample"] == 1


class _CountingGrader:
    """A grader with a `release()` that records how often it was called."""

    id = "counting@1"
    # Annotated for the reason JudgeGrader.kind is: a bare assignment infers
    # `str`, which `Sequence[Grader]` does not accept.
    kind: GraderKind = "deterministic"
    version = "1"

    def __init__(self) -> None:
        self.released = 0

    def grade(self, case, trajectory):
        del case, trajectory
        return Grade("counted", 1.0, True, "counted")

    def release(self) -> None:
        self.released += 1


class _PlainGrader:
    """The same grader without a `release()`, which `apply` must pass over."""

    id = "plain@1"
    # Annotated for the reason JudgeGrader.kind is: a bare assignment infers
    # `str`, which `Sequence[Grader]` does not accept.
    kind: GraderKind = "deterministic"
    version = "1"

    def grade(self, case, trajectory):
        del case, trajectory
        return Grade("plain", 1.0, True, "plain")


def test_release_is_called_only_on_a_releasable_grader():
    counting, plain = _CountingGrader(), _PlainGrader()
    assert isinstance(counting, Releasable) and not isinstance(plain, Releasable)
    out = apply(_run(), {c.name: c for c in _cases()}, [counting, plain], sample=None)
    assert counting.released == 1
    assert {g.dimension for g in out.cases[0].grades} >= {"counted", "plain"}


def test_a_deterministic_failure_survives_every_passing_judge(tmp_path: Path):
    """A judge can only add a way to fail. It never clears a case that a
    deterministic dimension already failed."""
    cases = [
        Case(
            name="c0",
            goal="q",
            target_requirements=["scripted"],
            script=_script(),
            expect=Expect(status="completed", answer_contains="Berlin"),
        )
    ]
    result = run_suite("s", cases, ScriptedTarget(), budget=Budget(max_usd=1, max_wall_s=60))
    assert result.cases[0].passed is False
    out = apply(
        result,
        {c.name: c for c in cases},
        [_judge(tmp_path, "j", ["VERDICT: SUPPORTED"]), HHEMGrader(scorer=StubScorer())],
        sample=None,
    )
    assert out.cases[0].passed is False
    assert all(g.passed for g in out.cases[0].grades if g.dimension != "answer_contains")


def test_apply_unknown_case_raises(tmp_path: Path):
    result = _run()
    with pytest.raises(ValueError, match="c0"):
        apply(result, {}, [_judge(tmp_path, "a", [])], sample=None)


def test_compute_metrics_omits_judge_keys_without_grades():
    m = compute_metrics([])
    assert not any(k.startswith("judge.") for k in m) and "unsupported_rate" not in m


CASE_YAML = (
    "goal: q\ntarget_requirements: [scripted]\nscript:\n"
    "  - {kind: tool, name: search, input: {}, output: Paris is in France.}\n"
    "  - {kind: model, name: final, input: {}, output: Paris is in France.,\n"
    "     answer: Paris is in France.}\n"
    "expect: {status: completed}\n"
)


def test_cli_judge_pass(tmp_path: Path):
    suite = tmp_path / "suite"
    suite.mkdir()
    for c in _cases():
        (suite / f"{c.name}.yaml").write_text(f"name: {c.name}\n{CASE_YAML}", encoding="utf-8")
    run = ["run", "offline", "--suite-dir", str(suite)]
    assert main([*run, "--target", "scripted", "--results", str(tmp_path / "r")]) == 0
    code = main(
        [
            "judge",
            "--suite-dir",
            str(suite),
            "--results",
            str(tmp_path / "r"),
            "--judge",
            "mockllm/model",
            "--cache",
            str(tmp_path / "c"),
        ]
    )
    assert code == 0
    latest = json.loads((tmp_path / "r" / "suite" / "latest.json").read_text())
    assert "judge.faithfulness.mockllm/model.unknown_rate" in latest["metrics"]
    assert main(["judge", "--suite-dir", str(suite), "--results", str(tmp_path / "none")]) == 2


def _scored_run(tmp_path: Path) -> Path:
    """A suite directory with one stored run under `tmp_path/r`, which is
    what `evalplat judge` needs before it builds a grader."""
    suite = tmp_path / "suite"
    suite.mkdir()
    for c in _cases():
        (suite / f"{c.name}.yaml").write_text(f"name: {c.name}\n{CASE_YAML}", encoding="utf-8")
    run = ["run", "offline", "--suite-dir", str(suite)]
    assert main([*run, "--target", "scripted", "--results", str(tmp_path / "r")]) == 0
    return suite


def _judge_argv(suite: Path, tmp_path: Path, model: str) -> list[str]:
    return [
        "judge",
        "--suite-dir",
        str(suite),
        "--results",
        str(tmp_path / "r"),
        "--judge",
        model,
        "--cache",
        str(tmp_path / "c"),
    ]


def test_cli_judge_rejects_a_sample_below_one(tmp_path: Path, capsys):
    suite = _scored_run(tmp_path)
    code = main([*_judge_argv(suite, tmp_path, "mockllm/model"), "--sample", "0"])
    assert code == 2 and "--sample must be at least 1" in capsys.readouterr().err


def test_cli_judge_exits_2_when_the_judge_has_no_local_snapshot(
    tmp_path: Path, capsys, monkeypatch
):
    suite = _scored_run(tmp_path)
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "empty-hub"))
    code = main(_judge_argv(suite, tmp_path, "hf/Org/Missing"))
    err = capsys.readouterr().err
    assert code == 2
    assert "no local snapshot for hf/Org/Missing" in err and "huggingface-cli download" in err
