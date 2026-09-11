import dataclasses

import pytest
from pydantic import ValidationError

from eval_platform.types import (
    Case,
    CaseResult,
    Expect,
    Fault,
    Grade,
    Step,
    Trajectory,
    compute_metrics,
)


def _traj(status="completed", cost=0.01, wall=100.0, tools=("lookup",)):
    steps = tuple(Step(kind="tool", name=t, input={}, output="ok") for t in tools)
    return Trajectory(
        target="t",
        goal="g",
        steps=steps,
        status=status,
        answer="a",
        side_effects=(),
        cost_usd=cost,
        wall_ms=wall,
        meta={},
    )


def test_trajectory_is_frozen_and_lists_tools_in_order():
    t = _traj(tools=("lookup", "send_email"))
    assert t.tools_used() == ["lookup", "send_email"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        t.status = "failed"  # type: ignore[misc]


def test_trajectory_to_dict_round_trips_steps():
    d = _traj().to_dict()
    assert d["steps"][0]["name"] == "lookup"
    assert d["status"] == "completed"


def test_case_rejects_unknown_keys():
    with pytest.raises(ValidationError):
        Case(name="x", goal="g", expect=Expect(), bogus=1)  # type: ignore[call-arg]


def test_expect_tools_used_accepts_only_known_modes():
    Expect(tools_used={"subset_of": ["lookup"]})
    with pytest.raises(ValidationError):
        Expect(tools_used={"sometimes": ["lookup"]})


def test_compute_metrics_percentiles_and_pass_rate():
    ok = CaseResult(name="a", passed=True, grades=(), trajectory=_traj(cost=0.01, wall=100))
    bad = CaseResult(name="b", passed=False, grades=(), trajectory=_traj(cost=0.03, wall=300))
    skipped = CaseResult(
        name="c", passed=False, grades=(), trajectory=None, skipped_reason="no target"
    )
    m = compute_metrics([ok, bad, skipped])
    assert m["cases_total"] == 3 and m["cases_passed"] == 1 and m["cases_skipped"] == 1
    assert m["pass_rate"] == 0.5  # skipped cases are excluded from the denominator
    assert m["usd_per_run_p50"] == pytest.approx(0.02)
    assert m["wall_ms_p95"] == pytest.approx(290.0)


def test_compute_metrics_with_no_trajectories_is_zero_not_error():
    m = compute_metrics([])
    assert m["pass_rate"] == 0.0 and m["wall_ms_p95"] == 0.0


def _recovery_case(name, observed, expected, passed):
    return CaseResult(
        name=name,
        passed=passed,
        grades=(
            Grade(dimension="recovered", value=observed, passed=passed, explanation=""),
            Grade(dimension="recovery_expected", value=expected, passed=True, explanation=""),
        ),
        trajectory=_traj(),
    )


def test_recovery_rate_and_expectation_match_rate_measure_different_things():
    """Four cases: two recover as expected, one was expected to recover and
    did not, and one correctly predicted a run that cannot come back. Only
    the first three count toward recovery_rate."""
    cases = [
        _recovery_case("a", observed=1.0, expected=1.0, passed=True),
        _recovery_case("b", observed=1.0, expected=1.0, passed=True),
        _recovery_case("c", observed=0.0, expected=1.0, passed=False),
        _recovery_case("d", observed=0.0, expected=0.0, passed=True),
    ]
    m = compute_metrics(cases)
    assert m["recovery_rate"] == pytest.approx(2 / 3)
    assert m["expectation_match_rate"] == pytest.approx(3 / 4)


def test_recovery_rate_is_omitted_when_no_case_expects_recovery():
    """A suite whose every fault case predicts a non-recovery reports the
    match rate and no recovery rate, since the mean would be over nothing."""
    m = compute_metrics([_recovery_case("d", observed=0.0, expected=0.0, passed=True)])
    assert "recovery_rate" not in m
    assert m["expectation_match_rate"] == 1.0


def test_neither_recovery_metric_appears_without_a_recovered_grade():
    m = compute_metrics([CaseResult(name="a", passed=True, grades=(), trajectory=_traj())])
    assert "recovery_rate" not in m and "expectation_match_rate" not in m


def _attack_case(name, succeeded=None, passed=True):
    grades = (
        ()
        if succeeded is None
        else (Grade(dimension="attack_succeeded", value=succeeded, passed=passed, explanation=""),)
    )
    return CaseResult(name=name, passed=passed, grades=grades, trajectory=_traj(), kind="attack")


def test_attack_success_rate_is_omitted_when_no_attack_case_was_graded():
    """An attack case carrying no attack_succeeded grade leaves the mean
    over nothing, and a published 0.0 there would read as every attack
    stopped. utility_rate still appears, since a scored attack case exists."""
    benign = CaseResult(name="b", passed=True, grades=(), trajectory=_traj())
    m = compute_metrics([_attack_case("a"), benign])
    assert "attack_success_rate" not in m
    assert m["utility_rate"] == 1.0


def test_attack_success_rate_is_the_mean_of_the_grades_that_exist():
    m = compute_metrics([_attack_case("a", succeeded=1.0), _attack_case("b", succeeded=0.0)])
    assert m["attack_success_rate"] == pytest.approx(0.5)


def test_fault_rejects_a_kind_its_seam_does_not_implement():
    """raise/malformed/empty are tool-only and retryable_error/fatal_error/
    truncated are provider-only; delay is the one kind both seams run."""
    with pytest.raises(ValidationError):
        Fault(at="provider", kind="raise", name="planner")
    with pytest.raises(ValidationError):
        Fault(at="tool", kind="truncated", name="lookup")
    Fault(at="tool", kind="delay", name="lookup")
    Fault(at="provider", kind="delay", name="planner")


def test_grade_value_is_in_unit_interval():
    with pytest.raises(ValueError):
        Grade(dimension="d", value=1.5, passed=True, explanation="")
