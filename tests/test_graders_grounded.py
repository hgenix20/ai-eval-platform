"""The quotes_in_source dimension: every quoted span in the answer has to
exist in what the tools actually returned."""

from typing import Any

from eval_platform.graders import grade_expect
from eval_platform.types import Case, CaseResult, Expect, Grade, Step, Trajectory, compute_metrics

SOURCE = (
    "The following summarizes factors that could have a material adverse "
    "effect on the Company's business, reputation, results of operations."
)


def _traj(answer: str, outputs: tuple[str, ...] = (SOURCE,)) -> Trajectory:
    steps: tuple[Step, ...] = tuple(
        Step("tool", "search_filing", {"query": "q"}, o) for o in outputs
    )
    return Trajectory(
        target="t",
        goal="g",
        steps=steps,
        status="completed",
        answer=answer,
        side_effects=(),
        cost_usd=0.0,
        wall_ms=1.0,
        meta={},
    )


def _grade(answer: str, outputs: tuple[str, ...] = (SOURCE,), **kw: Any) -> Grade | None:
    case = Case(name="c", goal="g", expect=Expect(grounded=True, **kw))
    grades = grade_expect(case, _traj(answer, outputs))
    return next((g for g in grades if g.dimension == "quotes_in_source"), None)


def test_a_quoted_span_that_exists_in_the_tool_output_passes():
    g = _grade('The filing says "The following summarizes factors that could have".')
    assert g is not None and g.passed and g.value == 1.0


def test_a_quoted_span_absent_from_the_tool_output_fails():
    g = _grade('The filing says "the company expects revenue to double next year".')
    assert g is not None and not g.passed and g.value == 0.0
    assert "the company expects revenue" in g.explanation


def test_the_explanation_names_only_the_first_60_characters_of_a_missing_span():
    missing = "z" * 200
    g = _grade(f'It says "{missing}".')
    assert g is not None and not g.passed
    assert "z" * 60 in g.explanation and "z" * 61 not in g.explanation


def test_curly_quotes_are_read_as_a_quoted_span():
    g = _grade("The filing says “The following summarizes factors that could” here.")
    assert g is not None and g.passed


def test_a_curly_span_absent_from_the_tool_output_fails():
    g = _grade("The filing says “revenue will double again next year” here.")
    assert g is not None and not g.passed


def test_an_answer_with_no_quoted_span_passes():
    g = _grade("The passage lists risks to the business.")
    assert g is not None and g.passed and g.explanation == "no quoted span"


def test_a_short_quoted_span_is_not_checked():
    """Under 20 characters is a word in scare quotes, not a citation."""
    g = _grade('The filing calls them "factors" here.')
    assert g is not None and g.passed and g.explanation == "no quoted span"


def test_case_and_whitespace_differences_do_not_fail_the_span():
    g = _grade('It says "the   FOLLOWING\nsummarizes  factors that could have".')
    assert g is not None and g.passed


def test_a_curly_apostrophe_in_the_answer_matches_a_straight_one_in_the_source():
    curly = chr(0x2019)
    g = _grade(f"It says “effect on the Company{curly}s business, reputation”.")
    assert g is not None and g.passed


def test_every_tool_output_is_searched_not_only_the_first():
    g = _grade(
        'It says "The following summarizes factors that could have".',
        outputs=("nothing useful here", SOURCE),
    )
    assert g is not None and g.passed


def test_a_run_with_no_tool_call_fails_a_quoted_span():
    g = _grade('It says "The following summarizes factors that could have".', outputs=())
    assert g is not None and not g.passed


def test_the_dimension_is_absent_unless_grounded_is_true():
    case = Case(name="c", goal="g", expect=Expect(grounded=False))
    assert grade_expect(case, _traj("x")) == []
    case = Case(name="c", goal="g", expect=Expect())
    assert grade_expect(case, _traj("x")) == []


def test_grounded_does_not_disturb_the_other_dimensions():
    g = _grade(
        'It says "The following summarizes factors that could have".',
        answer_contains="The following summarizes factors",
    )
    assert g is not None and g.passed
    case = Case(
        name="c",
        goal="g",
        expect=Expect(grounded=True, answer_contains="The following summarizes factors"),
    )
    dims = [x.dimension for x in grade_expect(case, _traj('It says "x".'))]
    assert dims == ["answer_contains", "quotes_in_source"]


def _result(name: str, grades: tuple[Grade, ...]) -> CaseResult:
    return CaseResult(name, all(g.passed for g in grades), grades, _traj("a"))


def test_quote_fidelity_rate_is_the_pass_rate_over_the_cases_carrying_it():
    cases = [
        _result("a", (Grade("quotes_in_source", 1.0, True, "ok"),)),
        _result("b", (Grade("quotes_in_source", 0.0, False, "missing"),)),
        _result("c", (Grade("quotes_in_source", 1.0, True, "ok"),)),
        _result("d", (Grade("status", 1.0, True, "ok"),)),
    ]
    assert compute_metrics(cases)["quote_fidelity_rate"] == 2 / 3


def test_quote_fidelity_rate_is_omitted_when_no_case_carries_the_dimension():
    assert "quote_fidelity_rate" not in compute_metrics(
        [_result("a", (Grade("status", 1.0, True, "ok"),))]
    )
