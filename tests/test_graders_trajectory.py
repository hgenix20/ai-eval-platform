from eval_platform.graders import grade_expect
from eval_platform.graders.trajectory import redundant_calls, step_efficiency
from eval_platform.types import Case, CaseResult, Expect, Grade, Step, Trajectory, compute_metrics


def _t(*tools, answer="ok", outputs=None):
    steps = tuple(
        Step("tool", name, {"key": name}, (outputs or {}).get(name, "v")) for name in tools
    )
    return Trajectory("t", "g", steps, "completed", answer, (), 0.0, 1.0, {})


def _g(expect, traj):
    return {g.dimension: g for g in grade_expect(Case(name="c", goal="g", expect=expect), traj)}


def test_redundant_calls_counts_repeated_tool_and_arguments():
    steps = (
        Step("tool", "lookup", {"key": "a"}, "v"),
        Step("tool", "lookup", {"key": "a"}, "v"),
        Step("tool", "lookup", {"key": "b"}, "v"),
        Step("model", "final", None, "x"),
    )
    assert redundant_calls(steps) == 1


def test_step_efficiency_bounds():
    assert step_efficiency(2, 2) == 1.0 and step_efficiency(2, 1) == 1.0
    assert step_efficiency(2, 4) == 0.5 and step_efficiency(0, 3) == 0.0


def test_forbidden_tools_dimension():
    assert _g(Expect(forbidden_tools=["send_email"]), _t("lookup"))["forbidden_tools"].passed
    assert not _g(Expect(forbidden_tools=["lookup"]), _t("lookup"))["forbidden_tools"].passed


def test_redundancy_and_efficiency_dimensions():
    traj = _t("lookup", "lookup", "recall")
    g = _g(Expect(max_redundant_calls=0, reference_steps=2, min_step_efficiency=0.7), traj)
    assert not g["max_redundant_calls"].passed
    assert g["step_efficiency"].value == 2 / 3 and not g["step_efficiency"].passed
    g2 = _g(Expect(reference_steps=3), traj)
    assert g2["step_efficiency"].passed and g2["step_efficiency"].value == 1.0


def test_tool_output_contains_dimension():
    traj = _t("recall", outputs={"recall": "the code word is heron"})
    assert _g(Expect(tool_output_contains={"tool": "recall", "text": "heron"}), traj)[
        "tool_output_contains"
    ].passed
    assert not _g(Expect(tool_output_contains={"tool": "recall", "text": "otter"}), traj)[
        "tool_output_contains"
    ].passed
    assert not _g(Expect(tool_output_contains={"tool": "lookup", "text": "heron"}), traj)[
        "tool_output_contains"
    ].passed


def test_step_efficiency_mean_metric():
    ok = CaseResult("a", True, (Grade("step_efficiency", 1.0, True, ""),), _t("lookup"))
    half = CaseResult("b", True, (Grade("step_efficiency", 0.5, True, ""),), _t("lookup"))
    none = CaseResult("c", True, (), _t("lookup"))
    m = compute_metrics([ok, half, none])
    assert m["step_efficiency_mean"] == 0.75
    assert "step_efficiency_mean" not in compute_metrics([none])
