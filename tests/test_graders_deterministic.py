from typing import Any

from eval_platform.graders import grade_expect
from eval_platform.types import Case, Expect, Step, Trajectory


def _traj(**kw: Any) -> Trajectory:
    base: dict[str, Any] = dict(
        target="t",
        goal="g",
        steps=(
            Step("tool", "lookup", None, "v"),
            Step("model", "proposed_answer", None, "the budget is 50k"),
        ),
        status="completed",
        answer="the budget is 50k",
        side_effects=(),
        cost_usd=0,
        wall_ms=1,
        meta={"history_types": ["tool_result", "proposed_answer"], "steps_used": 2},
    )
    base.update(kw)
    return Trajectory(**base)


def _grades(expect, traj):
    return {
        g.dimension: g.passed for g in grade_expect(Case(name="c", goal="g", expect=expect), traj)
    }


def test_all_dimensions_pass_on_matching_trajectory():
    e = Expect(
        status="completed",
        answer_contains="50k",
        side_effects=0,
        history_types=["tool_result", "proposed_answer"],
        max_steps_used=2,
        tools_used={"strict": ["lookup"]},
    )
    assert all(_grades(e, _traj()).values())


def test_each_dimension_fails_independently():
    assert _grades(Expect(status="failed"), _traj()) == {"status": False}
    assert _grades(Expect(answer_contains="99k"), _traj()) == {"answer_contains": False}
    assert _grades(Expect(side_effects=1), _traj()) == {"side_effects": False}
    assert _grades(Expect(max_steps_used=1), _traj()) == {"max_steps_used": False}
    assert _grades(Expect(history_types=["proposed_answer"]), _traj()) == {"history_types": False}


def test_tools_used_modes():
    t = _traj(steps=(Step("tool", "lookup", None, "v"), Step("tool", "recall", None, "v")))
    assert _grades(Expect(tools_used={"strict": ["lookup", "recall"]}), t)["tools_used"]
    assert not _grades(Expect(tools_used={"strict": ["recall", "lookup"]}), t)["tools_used"]
    assert _grades(Expect(tools_used={"unordered": ["recall", "lookup"]}), t)["tools_used"]
    assert _grades(Expect(tools_used={"subset_of": ["lookup", "recall", "send_email"]}), t)[
        "tools_used"
    ]
    assert not _grades(Expect(tools_used={"subset_of": ["lookup"]}), t)["tools_used"]


def test_empty_expect_yields_no_grades():
    assert grade_expect(Case(name="c", goal="g", expect=Expect()), _traj()) == []


def test_history_types_explicit_empty_list_is_graded_as_empty():
    t = _traj(steps=(Step("tool", "lookup", None, "v"),), meta={"history_types": []})
    assert _grades(Expect(history_types=[]), t) == {"history_types": True}
    assert _grades(Expect(history_types=["lookup"]), t) == {"history_types": False}


def test_side_effects_fails_when_the_target_cannot_observe_them():
    """An empty side-effect tuple from a target that never watched the
    executor is absence of evidence, so `side_effects: 0` must not pass on
    it. The grade fails and says why."""
    traj = _traj(
        side_effects=(),
        meta={
            "history_types": ["tool_result", "proposed_answer"],
            "steps_used": 2,
            "side_effects_unavailable": True,
        },
    )
    [grade] = grade_expect(Case(name="c", goal="g", expect=Expect(side_effects=0)), traj)
    assert grade.dimension == "side_effects" and grade.passed is False
    assert grade.explanation == "side effects are not observable on this target"
    # The same expectation on a target that does watch the executor passes.
    assert _grades(Expect(side_effects=0), _traj())["side_effects"] is True


def test_recovered_false_fails_when_a_fault_fired_but_the_run_still_completed():
    """A fault that fires but does not stop the run from completing is the
    one case `recovered: false` must reject: the case expected no
    recovery to be needed, but a fault fired anyway."""
    traj = _traj(status="completed", meta={"faults_fired": [{"kind": "raise"}]})
    [grade] = grade_expect(Case(name="c", goal="g", expect=Expect(recovered=False)), traj)
    assert grade.dimension == "recovered" and grade.passed is False
    assert grade.explanation == (
        "1 fault(s) fired and the run still completed, but the case expected no recovery"
    )
