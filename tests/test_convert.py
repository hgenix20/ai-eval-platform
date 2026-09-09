from eval_platform.targets.convert import run_dict_to_trajectory


def test_history_types_map_to_step_kinds():
    run = {
        "outcome": {"status": "completed", "answer": "revenue is 5"},
        "history": [
            {"type": "protocol_error", "detail": "bad"},
            {"type": "tool_result", "tool": "lookup", "output": "5"},
            {"type": "validator_feedback", "reason": "vague"},
            {"type": "proposed_answer", "answer": "revenue is 5"},
        ],
        "steps_used": 3,
    }
    t = run_dict_to_trajectory(run, target="t", goal="g", wall_ms=12.0, cost_usd=0.0)
    assert [s.kind for s in t.steps] == ["error", "tool", "error", "model"]
    assert t.tools_used() == ["lookup"] and t.answer == "revenue is 5" and t.meta["steps_used"] == 3


def test_missing_outcome_is_failed():
    t = run_dict_to_trajectory(
        {"outcome": None, "history": [], "steps_used": 0},
        target="t",
        goal="g",
        wall_ms=0,
        cost_usd=0,
    )
    assert t.status == "failed" and t.answer is None
