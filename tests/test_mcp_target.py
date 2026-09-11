import asyncio
import json
import sys
from pathlib import Path
from typing import ClassVar

import pytest
from inspect_ai.model import ChatMessageAssistant, ChatMessageTool, ChatMessageUser, ModelOutput
from inspect_ai.tool import ToolCall
from inspect_ai.tool._tool_call import ToolCallError

import eval_platform.cli as cli_mod
from eval_platform.targets import MCPTarget, TargetUnavailable
from eval_platform.targets.mcp import messages_to_trajectory
from eval_platform.types import Case, Expect

FIXTURE = str(Path(__file__).resolve().parent / "fixtures" / "mcp_fixture_server.py")


def _mock_target(outputs: list[ModelOutput], tmp_path: Path, **kw) -> MCPTarget:
    """The fixture server over stdio, driven by a scripted mockllm."""
    return MCPTarget.stdio(
        command=sys.executable,
        args=[FIXTURE],
        model="mockllm/model",
        model_args={"custom_outputs": outputs},
        log_dir=tmp_path,
        **kw,
    )


def _case(goal: str = "add 2 and 3", max_steps: int = 4) -> Case:
    return Case(name="mcp-add", goal=goal, max_steps=max_steps, expect=Expect(status="completed"))


def test_messages_to_trajectory_pairs_calls_with_results():
    """A hand-built conversation: one answered call, one failed call, one
    call with no result at all, then a plain reply as the answer."""
    messages = [
        ChatMessageUser(content="add 2 and 3"),
        ChatMessageAssistant(
            content="calling",
            tool_calls=[
                ToolCall(id="c1", function="add", arguments={"a": 2, "b": 3}),
                ToolCall(id="c2", function="echo", arguments={"text": "hi"}),
                ToolCall(id="c3", function="add", arguments={"a": 1, "b": 1}),
            ],
        ),
        ChatMessageTool(content="5", tool_call_id="c1", function="add"),
        ChatMessageTool(
            content="",
            tool_call_id="c2",
            function="echo",
            error=ToolCallError(type="unknown", message="boom"),
        ),
        ChatMessageAssistant(content="5"),
    ]
    t = messages_to_trajectory(
        messages,
        target="mcp:fixture",
        goal="add 2 and 3",
        cost_usd=0.25,
        wall_ms=12.0,
        meta={"model": "mockllm/model"},
    )
    assert t.tools_used() == ["add", "echo", "add"]
    assert t.steps[0].output == "5" and t.steps[0].error is None
    assert t.steps[0].input == {"a": 2, "b": 3}
    assert t.steps[1].error == "boom"
    assert t.steps[2].error == "no tool result" and t.steps[2].output is None
    assert t.answer == "5"
    assert t.status == "completed" and t.side_effects == ()
    assert t.cost_usd == 0.25 and t.wall_ms == 12.0
    assert t.meta["steps_used"] == 3
    assert t.meta["side_effects_unavailable"] is True
    assert t.meta["model"] == "mockllm/model"


def test_messages_to_trajectory_does_not_mutate_meta():
    meta = {"model": "m"}
    messages_to_trajectory(
        [], target="mcp:x", goal="g", cost_usd=0.0, wall_ms=0.0, meta=meta, status="failed"
    )
    assert meta == {"model": "m"}


def test_messages_to_trajectory_empty_conversation():
    t = messages_to_trajectory(
        [], target="mcp:x", goal="g", cost_usd=0.0, wall_ms=0.0, meta={}, status="failed"
    )
    assert t.steps == () and t.answer is None and t.status == "failed"


def test_target_name_and_capabilities():
    target = MCPTarget.stdio(command=sys.executable, args=[FIXTURE], model="mockllm/model")
    assert target.name.startswith(f"mcp:{Path(sys.executable).name}-")
    assert target.capabilities == frozenset({"agent", "mcp"})


def test_stdio_name_is_bounded_and_stable():
    """The fallback name has to fit in a results filename, and must not
    change between two targets built from the same command line."""
    first = MCPTarget.stdio(command=sys.executable, args=[FIXTURE], model="mockllm/model")
    second = MCPTarget.stdio(command=sys.executable, args=[FIXTURE], model="mockllm/model")
    assert first.name == second.name
    assert len(first.name) <= 60
    assert FIXTURE not in first.name and sys.executable not in first.name


def test_stdio_name_differs_for_a_different_command_line():
    first = MCPTarget.stdio(command=sys.executable, args=[FIXTURE], model="mockllm/model")
    other = MCPTarget.stdio(command=sys.executable, args=[FIXTURE, "-x"], model="mockllm/model")
    assert first.name != other.name


def test_explicit_server_name_wins():
    target = MCPTarget.stdio(
        command=sys.executable, args=[FIXTURE], model="mockllm/model", server_name="fixture"
    )
    assert target.name == "mcp:fixture"


def test_http_target_is_named_after_its_url():
    target = MCPTarget.http(url="https://example.invalid/mcp", model="mockllm/model")
    assert target.name == "mcp:https://example.invalid/mcp"


def test_list_tools_rejects_being_called_inside_an_event_loop():
    """A running loop is a caller bug, and must not be reported as an
    unreachable server."""
    target = MCPTarget.stdio(command=sys.executable, args=[FIXTURE], model="mockllm/model")

    async def call() -> list[str]:
        return target.list_tools()

    with pytest.raises(RuntimeError, match="must be called from synchronous code") as caught:
        asyncio.run(call())
    assert not isinstance(caught.value, TargetUnavailable)


def test_list_tools_reports_the_fixture_servers_tools():
    target = MCPTarget.stdio(command=sys.executable, args=[FIXTURE], model="mockllm/model")
    assert target.list_tools() == ["add", "echo"]


def test_list_tools_raises_target_unavailable_for_a_dead_server(tmp_path: Path):
    missing = str(tmp_path / "no_such_server.py")
    target = MCPTarget.stdio(command=sys.executable, args=[missing], model="mockllm/model")
    with pytest.raises(TargetUnavailable):
        target.list_tools()


def test_run_drives_the_fixture_server_and_returns_a_trajectory(tmp_path: Path):
    outputs = [
        ModelOutput.for_tool_call("mockllm", "add", {"a": 2, "b": 3}),
        ModelOutput.from_content("mockllm", "5"),
    ]
    t = _mock_target(outputs, tmp_path).run(_case())
    assert t.status == "completed"
    assert t.tools_used() == ["add"]
    assert "5" in str(t.steps[0].output)
    assert t.steps[0].input == {"a": 2, "b": 3}
    assert t.answer == "5"
    assert t.cost_usd == 0.0 and t.wall_ms > 0.0
    assert t.meta["inspect_status"] == "success"
    assert t.meta["message_limit"] == 8


def test_run_bounds_the_message_limit_by_the_targets_own_ceiling(tmp_path: Path):
    outputs = [ModelOutput.from_content("mockllm", "no tools needed")]
    t = _mock_target(outputs, tmp_path, max_steps=2).run(_case(max_steps=99))
    assert t.meta["message_limit"] == 4
    assert t.answer == "no tools needed" and t.steps == ()


def test_run_rejects_a_malformed_case(tmp_path: Path):
    target = _mock_target([ModelOutput.from_content("mockllm", "x")], tmp_path)
    with pytest.raises(ValueError, match="empty goal"):
        target.run(_case(goal=""))
    with pytest.raises(ValueError, match="max_steps"):
        target.run(_case(max_steps=0))


CASE_YAML = """
name: mcp-add
goal: add 2 and 3
target_requirements: [mcp]
max_steps: 4
expect: {status: completed, answer_contains: "5"}
"""


class _FakeMCPTarget:
    """Stands in for MCPTarget in the CLI parser tests: records how the CLI
    built it and replays one fixed trajectory per case."""

    built: ClassVar[dict] = {}
    name = "mcp:fake"
    capabilities = frozenset({"agent", "mcp"})

    @classmethod
    def stdio(cls, **kw):
        cls.built = {"kind": "stdio", **kw}
        return cls()

    @classmethod
    def http(cls, **kw):
        cls.built = {"kind": "http", **kw}
        return cls()

    def list_tools(self):
        return ["add", "echo"]

    def run(self, case: Case):
        return messages_to_trajectory(
            [
                ChatMessageAssistant(
                    content="calling",
                    tool_calls=[ToolCall(id="c1", function="add", arguments={"a": 2, "b": 3})],
                ),
                ChatMessageTool(content="5", tool_call_id="c1", function="add"),
                ChatMessageAssistant(content="5"),
            ],
            target=self.name,
            goal=case.goal,
            cost_usd=0.0,
            wall_ms=1.0,
            meta={},
        )


def _suite_dir(tmp_path: Path) -> Path:
    suite = tmp_path / "suites" / "mcp_smoke"
    suite.mkdir(parents=True)
    (suite / "add.yaml").write_text(CASE_YAML, encoding="utf-8")
    return suite


def test_cli_run_mcp_stdio_builds_the_target_and_runs_the_suite(
    tmp_path: Path, monkeypatch, capsys
):
    monkeypatch.setattr(cli_mod, "MCPTarget", _FakeMCPTarget)
    results = tmp_path / "results"
    code = cli_mod.main(
        [
            "run",
            "mcp",
            "--suite-dir",
            str(_suite_dir(tmp_path)),
            "--mcp-command",
            sys.executable,
            "--mcp-args",
            FIXTURE,
            "--model",
            "mockllm/model",
            "--model-args",
            '{"custom_outputs": []}',
            "--max-steps",
            "3",
            "--server-name",
            "fixture",
            "--results",
            str(results),
        ]
    )
    assert code == 0
    built = _FakeMCPTarget.built
    assert built["kind"] == "stdio" and built["command"] == sys.executable
    assert built["args"] == [FIXTURE] and built["max_steps"] == 3
    assert built["server_name"] == "fixture"
    assert built["model_args"] == {"custom_outputs": []} and built["log_dir"] is None
    out = capsys.readouterr().out
    assert "2 tools (add, echo)" in out and "mcp_smoke: 1/1 passed" in out
    summary = json.loads((results / "mcp_smoke" / "latest.json").read_text(encoding="utf-8"))
    assert summary["meta"]["mcp_tools"] == ["add", "echo"]


def test_cli_run_mcp_url_passes_the_authorization_token(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setattr(cli_mod, "MCPTarget", _FakeMCPTarget)
    code = cli_mod.main(
        [
            "run",
            "mcp",
            "--suite-dir",
            str(_suite_dir(tmp_path)),
            "--mcp-url",
            "https://example.invalid/mcp",
            "--mcp-authorization",
            "tok",
            "--model",
            "mockllm/model",
            "--results",
            str(tmp_path / "results"),
            "--log-dir",
            str(tmp_path / "logs"),
        ]
    )
    assert code == 0
    built = _FakeMCPTarget.built
    assert built["kind"] == "http" and built["url"] == "https://example.invalid/mcp"
    assert built["authorization"] == "tok" and built["log_dir"] == tmp_path / "logs"
    assert built["server_name"] is None
    capsys.readouterr()


def test_cli_run_mcp_requires_exactly_one_server_option(tmp_path: Path):
    with pytest.raises(SystemExit):
        cli_mod.main(
            ["run", "mcp", "--suite-dir", str(_suite_dir(tmp_path)), "--model", "mockllm/model"]
        )


def test_cli_run_mcp_unreachable_server_exits_2(tmp_path: Path, monkeypatch, capsys):
    class _Unreachable(_FakeMCPTarget):
        def list_tools(self):
            raise TargetUnavailable("nope")

    monkeypatch.setattr(cli_mod, "MCPTarget", _Unreachable)
    code = cli_mod.main(
        [
            "run",
            "mcp",
            "--suite-dir",
            str(_suite_dir(tmp_path)),
            "--mcp-url",
            "https://example.invalid/mcp",
            "--model",
            "mockllm/model",
        ]
    )
    assert code == 2
    assert "target unavailable: nope" in capsys.readouterr().err


def test_cli_run_mcp_rejects_malformed_model_args(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setattr(cli_mod, "MCPTarget", _FakeMCPTarget)
    code = cli_mod.main(
        [
            "run",
            "mcp",
            "--suite-dir",
            str(_suite_dir(tmp_path)),
            "--mcp-url",
            "https://example.invalid/mcp",
            "--model",
            "mockllm/model",
            "--model-args",
            "[1]",
        ]
    )
    assert code == 2
    assert "invalid --model-args JSON" in capsys.readouterr().err


@pytest.mark.network
def test_public_http_server_lists_tools():
    """A live remote MCP server answers a tool listing. Calls need a key;
    only the listing is asserted."""
    target = MCPTarget.http(url="https://mcp.signalnodus.ai/", model="mockllm/model")
    assert target.list_tools()
