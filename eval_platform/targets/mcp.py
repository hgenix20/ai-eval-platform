"""An MCP server as a system under test: an Inspect ReAct agent driving the
server's tools over stdio or HTTP, converted to this platform's Trajectory.

The platform does not reimplement the Model Context Protocol. Inspect owns
the transport (`mcp_server_stdio`, `mcp_server_http`) and the agent loop
(`react`); this module only builds the task, runs it, and converts the
resulting conversation into a `Trajectory` the graders already understand.
"""

from __future__ import annotations

import asyncio
import hashlib
import tempfile
from pathlib import Path
from typing import Any

from inspect_ai import Task
from inspect_ai import eval as inspect_eval

# PrerequisiteError has no public import path in Inspect 0.3.263.
from inspect_ai._util.error import PrerequisiteError
from inspect_ai.agent import react
from inspect_ai.dataset import Sample
from inspect_ai.model import ChatMessage, ChatMessageAssistant, ChatMessageTool
from inspect_ai.tool import MCPServer, ToolDef, mcp_server_http, mcp_server_stdio, mcp_tools

from eval_platform.targets.base import TargetUnavailable
from eval_platform.types import Case, Step, Trajectory


def _server_name(server: MCPServer) -> str:
    """The server's own human-readable name, as Inspect recorded it.

    Inspect keeps it on the private `_name` attribute of every concrete
    `MCPServer` (`mcp_server_stdio` defaults it to the command line,
    `mcp_server_http` to the URL); there is no public accessor. Falls back
    to the class name when the attribute is absent, so a third-party
    `MCPServer` implementation still yields a usable target name instead of
    raising.
    """
    name = getattr(server, "_name", None)
    return str(name) if name else type(server).__name__


def _stdio_name(command: str, args: list[str]) -> str:
    """A short, stable name for a stdio server: the executable's own file
    name, then the first 8 hex characters of the SHA-256 of the whole
    command line.

    Inspect names a stdio server after its entire command line, which on
    Windows is routinely 150 characters of absolute paths. That name reaches
    the target name, the trajectory, and the results filename
    `write_summary` builds, where an unbounded string is a path-length
    failure waiting to happen. This is bounded (the file name plus nine
    characters), stable for a given command line, and different for
    different ones, so two servers never collide in the results directory.
    The hash is a naming device, not a security control.

    Applied by `MCPTarget.stdio` rather than by `_server_name`, which sees
    only an already-built `MCPServer` and has no public way to tell a stdio
    server from an HTTP one, whose URL is short and worth keeping readable.
    """
    line = " ".join([command, *args])
    digest = hashlib.sha256(line.encode("utf-8")).hexdigest()[:8]
    return f"{Path(command).name}-{digest}"


def messages_to_trajectory(
    messages: list[ChatMessage],
    *,
    target: str,
    goal: str,
    cost_usd: float,
    wall_ms: float,
    meta: dict[str, Any],
    status: str = "completed",
) -> Trajectory:
    """Convert one Inspect conversation into a `Trajectory`. Pure: reads
    `messages` and its arguments only, and never touches a model, a server,
    or the filesystem.

    Contract: every `ToolCall` on every `ChatMessageAssistant` becomes one
    `Step(kind="tool", name=call.function, input=call.arguments)`, in call
    order. Its `output` is the text of the `ChatMessageTool` whose
    `tool_call_id` matches, and its `error` is that message's error text
    when the tool failed. A tool call with no matching tool message (the
    run ended before the call returned) keeps `output=None` and records
    `error="no tool result"`, so a truncated run is visible as a step
    rather than absent from the trajectory.

    `answer` is the text of the last `ChatMessageAssistant` that made no
    tool calls, or None when the agent never produced a plain reply.
    `side_effects` is always empty: an MCP server's effects happen inside
    the server, where this target cannot observe them, so `meta` carries
    `side_effects_unavailable: True` and a case asserting on side effects
    fails rather than passing on an empty tuple.

    `status` is supplied by the caller, not derived here: whether the run
    completed is a property of the Inspect sample (its `error` field), not
    of the message list, and this function never sees the sample.

    `meta` is copied, not aliased, so a caller's dict is not mutated by the
    keys added here (`steps_used`, `side_effects_unavailable`).

    Raises nothing: a malformed or empty message list yields a trajectory
    with no steps and no answer.
    """
    results: dict[str, ChatMessageTool] = {
        m.tool_call_id: m for m in messages if isinstance(m, ChatMessageTool) and m.tool_call_id
    }
    steps: list[Step] = []
    answer: str | None = None
    for m in messages:
        if not isinstance(m, ChatMessageAssistant):
            continue
        if not m.tool_calls:
            answer = m.text
            continue
        for call in m.tool_calls:
            result = results.get(call.id)
            steps.append(
                Step(
                    kind="tool",
                    name=call.function,
                    input=call.arguments,
                    output=result.text if result is not None else None,
                    error=_step_error(result),
                )
            )
    return Trajectory(
        target=target,
        goal=goal,
        steps=tuple(steps),
        status=status,
        answer=answer,
        side_effects=(),
        cost_usd=cost_usd,
        wall_ms=wall_ms,
        meta={**meta, "steps_used": len(steps), "side_effects_unavailable": True},
    )


def _step_error(result: ChatMessageTool | None) -> str | None:
    """The error text for one tool step: "no tool result" when the call
    never returned, the tool error's message when it failed, else None."""
    if result is None:
        return "no tool result"
    return str(result.error.message) if result.error is not None else None


class MCPTarget:
    """Runs a `Case` by pointing an Inspect ReAct agent at one MCP server.

    `name` is `"mcp:<server name>"`, where the server name is the command
    line (stdio) or the URL (HTTP) unless one was given explicitly.
    `capabilities` is `{"agent", "mcp"}`: this target runs an agent loop,
    but it cannot report side effects or drive an approval flow, so cases
    requiring those are not routed here.

    The agent runs with Inspect's `submit` tool disabled, so the run ends
    when the model replies without calling a tool, and that reply is the
    answer. With `submit` enabled the final answer would arrive as another
    tool call instead, which is a worse fit for this platform's
    `Trajectory` shape (tool steps are the agent's actions, not its
    answer).
    """

    capabilities = frozenset({"agent", "mcp"})

    def __init__(
        self,
        *,
        server: MCPServer,
        model: str,
        max_steps: int = 8,
        model_args: dict[str, Any] | None = None,
        log_dir: Path | None = None,
        server_name: str | None = None,
    ) -> None:
        """Bind this target to an already-built Inspect `MCPServer`.

        `model` is the Inspect model id the agent runs on (e.g.
        `"mockllm/model"`). `max_steps` is this target's own ceiling on
        agent steps; a case's `max_steps` is bounded by it (see `run`).
        `model_args` is forwarded to Inspect's model constructor.
        `log_dir` is where Inspect writes its `.eval` logs; when None,
        each `run` uses a temporary directory that is deleted afterwards,
        so a throwaway run leaves nothing behind. `server_name` overrides
        the name read off `server` for this target's `name`.

        Does not connect to the server: construction is cheap and cannot
        fail on a server being down. Use `list_tools()` to check
        reachability before running a suite.
        """
        self._server = server
        self._model = model
        self._max_steps = max_steps
        self._model_args = model_args
        self._log_dir = log_dir
        self.name = f"mcp:{server_name or _server_name(server)}"

    @classmethod
    def stdio(cls, *, command: str, args: list[str], model: str, **kw: Any) -> MCPTarget:
        """Target for an MCP server run as a child process over stdio.

        `command` is the executable and `args` its arguments; Inspect spawns
        the process and speaks JSON-RPC over its stdin/stdout. Every other
        keyword goes to `__init__`.

        The target's name defaults to `_stdio_name(command, args)`, which is
        bounded and stable, rather than to Inspect's own name for the server
        (the whole command line). Pass `server_name` to override it.

        Raises `TargetUnavailable` when the `mcp` package is not installed
        (`pip install -e ".[mcp]"`), since without it no MCP server can be
        reached at all.
        """
        # get(...) or ..., not setdefault: the CLI always passes the keyword,
        # with None meaning "no --server-name given".
        kw["server_name"] = kw.get("server_name") or _stdio_name(command, args)
        return cls(server=_stdio_server(command, args), model=model, **kw)

    @classmethod
    def http(
        cls, *, url: str, model: str, authorization: str | None = None, **kw: Any
    ) -> MCPTarget:
        """Target for a remote MCP server reached over streamable HTTP.

        `url` is the server endpoint and `authorization` an optional OAuth
        bearer token. Every other keyword goes to `__init__`.

        Raises `TargetUnavailable` when the `mcp` package is not installed.
        The URL itself is not contacted here; a bad URL or a down server
        appears on the first `list_tools()` or `run()`.
        """
        return cls(server=_http_server(url, authorization), model=model, **kw)

    def list_tools(self) -> list[str]:
        """The names of the tools this server offers, in the server's order.

        Connects to the server, reads its tool list, and disconnects. This
        is the cheapest reachability check available: a server that answers
        here is one an agent can use.

        Must be called from synchronous code: it drives its own loop through
        `asyncio.run`. A running event loop is a caller bug, not a server
        problem, so it is detected up front and raises `RuntimeError` naming
        the misuse; letting `asyncio.run` raise instead would send that
        RuntimeError into the connection-failure path below and report a
        healthy server as unreachable.

        Raises `TargetUnavailable` when the server cannot be reached or
        rejects the connection (process failed to start, URL unreachable,
        authorization refused). The transport raises a wide range of
        exception types through several layers, including exception groups,
        so every non-exiting exception from the connection itself is treated
        as unreachable and the original is attached as the cause.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass  # No loop running, which is what this method needs.
        else:
            raise RuntimeError(
                "MCPTarget.list_tools() must be called from synchronous code; "
                "a running event loop was detected"
            )

        async def _names() -> list[str]:
            async with self._server as session:
                return [ToolDef(t).name for t in await session.tools()]

        try:
            return asyncio.run(_names())
        except Exception as e:
            raise TargetUnavailable(f"{self.name} not reachable: {e}") from e

    def run(self, case: Case) -> Trajectory:
        """Run `case.goal` as an Inspect ReAct agent over this server's tools.

        Builds a one-sample task, evaluates it with `display="none"`, and
        converts the sample's conversation through `messages_to_trajectory`.
        The message limit is `2 * min(case.max_steps, self._max_steps)`: two
        messages per step (the assistant's call and the tool's reply), and
        the target's own ceiling bounds a case that asks for more.

        `status` is `"completed"` when the sample carries no error, else
        `"failed"`. `cost_usd` is the summed `total_cost` Inspect recorded
        across models, 0.0 when it recorded none (`mockllm` always).
        `wall_ms` is the sample's `total_time` in milliseconds, 0.0 when
        Inspect did not record one.

        Raises `ValueError` when `case.goal` is empty, when `case.max_steps`
        is not positive, or when Inspect returns a log with no samples
        (nothing ran, so there is nothing to report). An exception raised by
        Inspect itself (a model provider rejecting the request, a transport
        failure mid-run) propagates unchanged: it is a fault in the run, not
        a verdict on the case.
        """
        if not case.goal:
            raise ValueError(f"case {case.name} has an empty goal")
        if case.max_steps <= 0:
            raise ValueError(f"case {case.name} has max_steps {case.max_steps}, expected >= 1")
        message_limit = 2 * min(case.max_steps, self._max_steps)
        task = Task(
            dataset=[Sample(input=case.goal)],
            solver=react(tools=[mcp_tools(self._server)], submit=False),
        )
        if self._log_dir is not None:
            return self._eval(task, case, self._log_dir, message_limit)
        with tempfile.TemporaryDirectory(prefix="evalplat-mcp-") as tmp:
            return self._eval(task, case, Path(tmp), message_limit)

    def _eval(self, task: Task, case: Case, log_dir: Path, message_limit: int) -> Trajectory:
        """Run one built task and convert its single sample. Split out of
        `run` so both the caller-supplied and temporary log-directory paths
        share one body; see `run` for the contract."""
        [log] = inspect_eval(
            task,
            model=self._model,
            model_args=self._model_args or {},
            log_dir=str(log_dir),
            display="none",
            message_limit=message_limit,
        )
        if not log.samples:
            raise ValueError(f"Inspect returned no samples for case {case.name} on {self.name}")
        sample = log.samples[0]
        cost_usd = sum(float(u.total_cost or 0.0) for u in log.stats.model_usage.values())
        meta: dict[str, Any] = {
            "model": self._model,
            "log_location": log.location,
            "inspect_status": log.status,
            "message_limit": message_limit,
        }
        if sample.error is not None:
            meta["error"] = str(sample.error.message)
        return messages_to_trajectory(
            list(sample.messages),
            target=self.name,
            goal=case.goal,
            cost_usd=cost_usd,
            wall_ms=(sample.total_time or 0.0) * 1000.0,
            meta=meta,
            status="completed" if sample.error is None else "failed",
        )


def _stdio_server(command: str, args: list[str]) -> MCPServer:
    """Build Inspect's stdio MCP server, turning a missing `mcp` package
    into `TargetUnavailable` instead of Inspect's own PrerequisiteError."""
    try:
        return mcp_server_stdio(command=command, args=args)
    except PrerequisiteError as e:
        raise TargetUnavailable(f"mcp package not installed: {e}") from e


def _http_server(url: str, authorization: str | None) -> MCPServer:
    """Build Inspect's streamable-HTTP MCP server, turning a missing `mcp`
    package into `TargetUnavailable` instead of Inspect's own
    PrerequisiteError."""
    try:
        return mcp_server_http(url=url, authorization=authorization)
    except PrerequisiteError as e:
        raise TargetUnavailable(f"mcp package not installed: {e}") from e
