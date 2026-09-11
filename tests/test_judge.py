from pathlib import Path

import pytest
from inspect_ai.model import ModelOutput, get_model

from eval_platform.graders.judge import RUBRICS, JudgeGrader, parse_verdict
from eval_platform.graders.judge_cache import JudgeCache
from eval_platform.types import Case, Expect, Step, Trajectory


def _traj(answer: str, context: str = "Paris is the capital of France.") -> Trajectory:
    return Trajectory(
        target="t",
        goal="capital of France?",
        status="completed",
        answer=answer,
        steps=(Step("tool", "search", {"q": "France"}, context),),
        side_effects=(),
        cost_usd=0.0,
        wall_ms=1.0,
    )


def _case() -> Case:
    return Case(name="c1", goal="capital of France?", expect=Expect(answer_contains="Paris"))


def _grader(tmp_path: Path, outputs: list[str]) -> JudgeGrader:
    # mockllm's custom_outputs must be ModelOutput instances, not raw text
    # (confirmed against inspect_ai 0.3.263: a bare str fails its isinstance
    # check on the first generate() call).
    scripted = [ModelOutput.from_content(model="mockllm", content=text) for text in outputs]
    handle = get_model("mockllm/model", custom_outputs=scripted)
    return JudgeGrader(
        model="mockllm/model",
        rubric=RUBRICS["faithfulness"],
        cache=JudgeCache(tmp_path),
        model_handle=handle,
    )


@pytest.mark.parametrize(
    "text,label",
    [
        ("Reasoning...\nVERDICT: SUPPORTED", "SUPPORTED"),
        ("verdict: unsupported", "UNSUPPORTED"),
        ("VERDICT: UNKNOWN", "UNKNOWN"),
        ("I think it is fine.", "UNKNOWN"),
        ("VERDICT: SUPPORTED\nVERDICT: UNSUPPORTED", "UNSUPPORTED"),  # last line wins
        # A verdict word inside a sentence is prose, not the label: only a
        # line of its own counts.
        ("my verdict: leaning supported\nVERDICT: UNSUPPORTED", "UNSUPPORTED"),
        ("the verdict: SUPPORTED is tentative", "UNKNOWN"),
    ],
)
def test_parse_verdict(text, label):
    assert parse_verdict(text, RUBRICS["faithfulness"].labels) == label


def test_judge_pass_fail_unknown(tmp_path: Path):
    g = _grader(tmp_path, ["VERDICT: SUPPORTED", "VERDICT: UNSUPPORTED", "no idea"])
    r1 = g.judge(_case(), _traj("Paris."))
    assert (r1.verdict, r1.label, r1.cached) == ("pass", "SUPPORTED", False)
    r2 = g.judge(_case(), _traj("Berlin."))
    assert (r2.verdict, r2.label) == ("fail", "UNSUPPORTED")
    r3 = g.judge(_case(), _traj("Rome."))
    assert (r3.verdict, r3.label) == ("unknown", "UNKNOWN")


def test_judge_cache_hit_makes_no_call(tmp_path: Path):
    g = _grader(tmp_path, ["VERDICT: SUPPORTED"])  # exactly one scripted output
    first = g.judge(_case(), _traj("Paris."))
    second = g.judge(_case(), _traj("Paris."))  # a second call would exhaust mockllm
    assert first.cached is False and second.cached is True
    assert second.label == "SUPPORTED"


def test_grade_shape(tmp_path: Path):
    g = _grader(tmp_path, ["VERDICT: UNKNOWN"])
    grade = g.grade(_case(), _traj("Paris."))
    assert grade.dimension == "judge:faithfulness:mockllm/model"
    assert grade.value == 0.5 and grade.passed is False
    assert g.id == "faithfulness@1:mockllm/model" and g.version == "mock"


def test_judge_records_span(tmp_path: Path, spans):
    g = _grader(tmp_path, ["VERDICT: SUPPORTED"])
    g.judge(_case(), _traj("Paris."))
    g.judge(_case(), _traj("Paris."))
    names = [s.name for s in spans.get_finished_spans()]
    assert names.count("eval.grader") == 2
    hits = [
        s.attributes["eval.cache_hit"]
        for s in spans.get_finished_spans()
        if s.name == "eval.grader"
    ]
    assert hits == [False, True]
    s = spans.get_finished_spans()[0]
    assert s.attributes["eval.judge"] == "faithfulness@1:mockllm/model"


def test_faithfulness_prompt_carries_context_and_answer():
    text = RUBRICS["faithfulness"].user_prompt(_case(), _traj("Paris.", context="CTX-123"))
    assert "CTX-123" in text and "Paris." in text


def test_correctness_prompt_uses_reference():
    case = Case(name="c", goal="q?", expect=Expect(answer_contains="42"))
    text = RUBRICS["correctness"].user_prompt(case, _traj("It is 42."))
    assert "42" in text and "It is 42." in text


def test_release_drops_the_model_handle(tmp_path: Path):
    """release() lets go of the loaded model so the next judge can have the
    GPU; the cached verdict still answers a repeat call with no handle."""
    g = _grader(tmp_path, ["VERDICT: SUPPORTED"])  # exactly one scripted output
    g.judge(_case(), _traj("Paris."))
    g.release()
    assert g._handle is None
    again = g.judge(_case(), _traj("Paris."))
    assert again.cached is True and again.label == "SUPPORTED"


def test_empty_answer_is_unknown_without_a_call(tmp_path: Path):
    g = _grader(tmp_path, [])  # no scripted outputs: any call would fail
    r = g.judge(_case(), _traj(""))
    assert r.verdict == "unknown" and r.cached is False
