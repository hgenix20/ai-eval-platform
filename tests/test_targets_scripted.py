import pytest

from eval_platform.targets import ScriptedTarget
from eval_platform.types import Case, Expect


def test_scripted_target_replays_script_into_trajectory():
    case = Case(
        name="s",
        goal="g",
        expect=Expect(),
        script=[
            {
                "kind": "tool",
                "name": "lookup",
                "input": {"key": "x"},
                "output": "v",
                "latency_ms": 5,
                "cost_usd": 0.001,
            },
            {
                "kind": "model",
                "name": "final",
                "output": "done",
                "status": "completed",
                "answer": "done",
            },
        ],
    )
    t = ScriptedTarget().run(case)
    assert t.target == "scripted" and t.status == "completed" and t.answer == "done"
    assert t.tools_used() == ["lookup"] and t.cost_usd == 0.001 and t.wall_ms == 5


def test_scripted_target_requires_a_script():
    with pytest.raises(ValueError, match="script"):
        ScriptedTarget().run(Case(name="s", goal="g", expect=Expect()))


def test_scripted_target_rejects_item_missing_kind_or_name():
    case = Case(name="s", goal="g", expect=Expect(), script=[{"name": "final"}])
    with pytest.raises(ValueError, match="lacks 'kind' or 'name'"):
        ScriptedTarget().run(case)
