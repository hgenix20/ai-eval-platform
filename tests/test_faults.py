import pytest

pytest.importorskip("agent_platform")

from eval_platform.targets import AgentPlatformLocalTarget
from eval_platform.types import Case, Expect, Fault

pytestmark = pytest.mark.agent_platform


def _case(faults, planner, validator=None, expect=None, max_steps=5):
    return Case(
        name="f",
        goal="look up revenue and answer",
        faults=faults,
        max_steps=max_steps,
        planner=planner,
        validator=validator or ['{"approved": true, "reason": "ok"}'],
        expect=expect or Expect(),
    )


def test_tool_raise_is_recorded_and_run_outcome_reported():
    case = _case(
        [Fault(at="tool", name="lookup", kind="raise")],
        [
            '{"action": "tool", "tool": "lookup", "arguments": {"key": "revenue"}}',
            '{"action": "final", "answer": "gave up"}',
        ],
    )
    t = AgentPlatformLocalTarget().run(case)
    assert t.meta["faults_fired"] and t.meta["faults_fired"][0]["kind"] == "raise"
    # F4 in docs/red-team-findings.md: ToolExecutor.execute does not catch a
    # handler exception, so the run aborts and the local target's exception
    # boundary reports target_error. Pinned exactly, so a platform fix that
    # lets the model see a tool_error shows up here as a failure to update.
    assert t.status == "target_error"


def test_malformed_tool_output_reaches_the_model_as_text():
    case = _case(
        [Fault(at="tool", name="lookup", kind="malformed")],
        [
            '{"action": "tool", "tool": "lookup", "arguments": {"key": "x"}}',
            '{"action": "final", "answer": "handled"}',
        ],
    )
    t = AgentPlatformLocalTarget().run(case)
    tool_steps = [s for s in t.steps if s.kind == "tool"]
    assert tool_steps and "malformed" in str(tool_steps[0].output)


def test_retryable_provider_error_falls_back_when_a_fallback_route_exists():
    case = _case(
        [Fault(at="provider", name="planner", kind="retryable_error", times=1)],
        ['{"action": "final", "answer": "after fallback"}'],
    )
    t = AgentPlatformLocalTarget().run(case)
    assert t.status == "completed" and t.answer == "after fallback"
    assert t.meta["faults_fired"][0]["kind"] == "retryable_error"


def test_fatal_provider_error_ends_the_run():
    case = _case(
        [Fault(at="provider", name="planner", kind="fatal_error")],
        ['{"action": "final", "answer": "never"}'],
    )
    t = AgentPlatformLocalTarget().run(case)
    assert t.status != "completed"


def test_a_masking_fault_leaves_later_arguments_on_their_own_step():
    """The recorder wraps the fault wrapper, so a fault that returns before
    the real handler still records its own call. With the two nested the
    other way round, the malformed first call recorded nothing and the
    second call's arguments slid onto the first tool step."""
    case = _case(
        [Fault(at="tool", name="lookup", kind="malformed", times=1)],
        [
            '{"action": "tool", "tool": "lookup", "arguments": {"key": "a"}}',
            '{"action": "tool", "tool": "lookup", "arguments": {"key": "b"}}',
            '{"action": "final", "answer": "done"}',
        ],
    )
    t = AgentPlatformLocalTarget().run(case)
    tool_steps = [s for s in t.steps if s.kind == "tool"]
    assert [s.input for s in tool_steps] == [{"key": "a"}, {"key": "b"}]


def test_truncated_reply_becomes_protocol_error_then_recovers():
    case = _case(
        [Fault(at="provider", name="planner", kind="truncated", times=1)],
        ['{"action": "final", "answer": "first"}', '{"action": "final", "answer": "second"}'],
    )
    t = AgentPlatformLocalTarget().run(case)
    assert t.meta["history_types"][0] == "protocol_error" and t.answer == "second"
