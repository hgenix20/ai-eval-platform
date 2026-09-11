import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from inspect_ai.model import ModelOutput, get_model

from eval_platform.budget import Budget
from eval_platform.cli import main
from eval_platform.graders.hhem import HHEMGrader
from eval_platform.graders.judge import RUBRICS, JudgeGrader
from eval_platform.graders.judge_cache import JudgeCache
from eval_platform.judge_pass import apply
from eval_platform.results import summary_to_result, write_summary
from eval_platform.suites.runner import run_suite
from eval_platform.targets.scripted import ScriptedTarget
from eval_platform.types import Case, Expect, compute_metrics


def _cases():
    return [
        Case(
            name=f"c{n}",
            goal="q",
            target_requirements=["scripted"],
            script=[
                {"kind": "tool", "name": "search", "input": {}, "output": "Paris is in France."},
                # ScriptedTarget reads the trajectory's answer from the script's
                # own `answer` key, and a judge scores the answer: without this
                # the trajectory answers nothing and every verdict is unknown.
                {
                    "kind": "model",
                    "name": "final",
                    "input": {},
                    "output": "Paris is in France.",
                    "answer": "Paris is in France.",
                },
            ],
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
    assert out.meta["judge_pass"]["graders"][0] == "faithfulness@1:mockllm/a"


def test_apply_replaces_same_dimension_and_respects_sample(tmp_path: Path):
    result = _run()
    a = _judge(tmp_path, "a", ["VERDICT: UNSUPPORTED"] * 3 + ["VERDICT: SUPPORTED"] * 3)
    once = apply(result, {c.name: c for c in _cases()}, [a], sample=2)
    assert sum(1 for c in once.cases for g in c.grades if g.dimension.startswith("judge:")) == 2
    twice = apply(once, {c.name: c for c in _cases()}, [a], sample=2)  # cache hits, same grades
    assert [g.dimension for g in twice.cases[0].grades].count("judge:faithfulness:mockllm/a") == 1


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
