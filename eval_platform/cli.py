"""evalplat: catalog, run offline, public and mcp, gate, report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from eval_platform.budget import Budget, BudgetExceeded, Ledger
from eval_platform.catalog import filter_entries, load_catalog
from eval_platform.gate import compare, load_gate_config, to_junit, to_markdown
from eval_platform.reports import render_html
from eval_platform.results import latest_summary, read_summary, write_summary
from eval_platform.suites import load_cases, run_public, run_suite
from eval_platform.targets import (
    AgentPlatformHttpTarget,
    AgentPlatformLocalTarget,
    MCPTarget,
    ScriptedTarget,
    TargetUnavailable,
)
from eval_platform.targets.base import AgentTarget


def _target(name: str, base_url: str | None) -> AgentTarget:
    """Build the named target. Raises SystemExit for an unrecognized name
    (argparse's own choice validation never lets one through in practice);
    an `agent-platform-http` target may itself raise TargetUnavailable if
    it cannot reach `base_url`, which callers are expected to catch."""
    if name == "scripted":
        return ScriptedTarget()
    if name == "agent-platform-local":
        return AgentPlatformLocalTarget()
    if name == "agent-platform-http":
        return AgentPlatformHttpTarget(base_url or "http://127.0.0.1:8000")
    raise SystemExit(f"unknown target {name}")


def cmd_catalog(a: argparse.Namespace) -> int:
    """List catalog entries matching the given filters, one row per entry
    as "id  category  status  runner  license", followed by a count line.
    Always returns 0.
    """
    entries = filter_entries(
        load_catalog(Path(a.catalog)),
        category=a.category,
        status=a.status,
        runnable=True if a.runnable else None,
    )
    for e in entries:
        runner = e.runner.kind + ":" + (e.runner.ref or "")
        print(f"{e.id:24} {e.category:13} {e.status:23} {runner:48} {e.license.status}")
    print(f"{len(entries)} entries")
    return 0


def cmd_run_offline(a: argparse.Namespace) -> int:
    """Run every case under `--suite-dir` against `--target` and write the
    summary to `--results`. Prints the pass count and, for each failing
    case, its name and reason. An `agent-platform-http` target is closed
    once the run finishes, whether it succeeds or raises.

    Returns 2 if the target is unavailable (server unreachable, extra not
    installed); 0 otherwise, regardless of how many cases failed, since a
    failing suite is still a completed run for this command's purposes
    (the gate, not this command, decides pass/fail for CI).
    """
    try:
        target = _target(a.target, a.base_url)
    except TargetUnavailable as e:
        print(f"target unavailable: {e}", file=sys.stderr)
        return 2
    try:
        suite_dir = Path(a.suite_dir)
        result = run_suite(
            suite_dir.name,
            load_cases(suite_dir),
            target,
            budget=Budget(max_usd=a.budget_usd, max_wall_s=a.max_wall_s),
        )
    finally:
        # Only the HTTP target owns a network connection worth releasing;
        # scripted and in-process targets have nothing to close.
        if isinstance(target, AgentPlatformHttpTarget):
            target.close()
    path = write_summary(result, Path(a.results))
    passed = int(result.metrics["cases_passed"])
    total = int(result.metrics["cases_total"])
    print(f"{result.suite}: {passed}/{total} passed -> {path}")
    for c in result.cases:
        if not c.passed:
            why = c.skipped_reason or "; ".join(g.explanation for g in c.grades if not g.passed)
            print(f"  FAIL {c.name}: {why}")
    return 0


def _generate_config(a: argparse.Namespace) -> dict[str, Any] | None:
    """Build the `generate` dict for `run_public` from whichever of
    `--temperature`, `--max-tokens`, `--extra-body` were given on `a`, or
    None if none were. `--extra-body` is parsed as JSON; the caller must
    catch `json.JSONDecodeError` and turn it into exit code 2 rather than
    let it propagate as a traceback.
    """
    generate: dict[str, Any] = {}
    if a.temperature is not None:
        generate["temperature"] = a.temperature
    if a.max_tokens is not None:
        generate["max_tokens"] = a.max_tokens
    if a.extra_body is not None:
        generate["extra_body"] = json.loads(a.extra_body)
    return generate or None


def _model_args(a: argparse.Namespace) -> dict[str, Any] | None:
    """Parse `--model-args` (a JSON object of Inspect model constructor
    keyword arguments, e.g. `device`, `dtype` for the `hf/` provider)
    into a dict, or None if the option was not given.

    Raises `json.JSONDecodeError` on malformed JSON and `ValueError` when
    the parsed JSON is not an object (e.g. a list or a scalar); the caller
    must catch both and turn them into exit code 2 rather than let them
    propagate as a traceback.
    """
    if a.model_args is None:
        return None
    parsed = json.loads(a.model_args)
    if not isinstance(parsed, dict):
        raise ValueError(f"--model-args must be a JSON object, got {type(parsed).__name__}")
    return parsed


def _task_args(a: argparse.Namespace) -> dict[str, Any] | None:
    """Parse `--task-args` (a JSON object of keyword arguments for the
    Inspect task function itself, e.g. `with_sandbox_tasks` for
    `inspect_evals/agentdojo`) into a dict, or None if the option was not
    given.

    Raises `json.JSONDecodeError` on malformed JSON and `ValueError` when
    the parsed JSON is not an object (e.g. a list or a scalar); the caller
    must catch both and turn them into exit code 2 rather than let them
    propagate as a traceback.
    """
    if a.task_args is None:
        return None
    parsed = json.loads(a.task_args)
    if not isinstance(parsed, dict):
        raise ValueError(f"--task-args must be a JSON object, got {type(parsed).__name__}")
    return parsed


class _CliOptionError(Exception):
    """Carries a ready-to-print message for one invalid `run public` JSON
    option (`--extra-body`, `--model-args`, `--task-args`). Raised by
    `_parse_public_options` so `cmd_run_public` needs only one
    `except`/`return 2` for all three, instead of one pair per option."""


def _parse_public_options(
    a: argparse.Namespace,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    """Parse `--extra-body`/`--temperature`/`--max-tokens` into `generate`,
    `--model-args` into `model_args`, and `--task-args` into `task_args`,
    returning all three. Raises `_CliOptionError` with a message naming the
    offending option on the first parse failure.
    """
    try:
        generate = _generate_config(a)
    except json.JSONDecodeError as e:
        raise _CliOptionError(f"invalid --extra-body JSON: {e}") from e
    try:
        model_args = _model_args(a)
    except (json.JSONDecodeError, ValueError) as e:
        raise _CliOptionError(f"invalid --model-args JSON: {e}") from e
    try:
        task_args = _task_args(a)
    except (json.JSONDecodeError, ValueError) as e:
        raise _CliOptionError(f"invalid --task-args JSON: {e}") from e
    return generate, model_args, task_args


def cmd_run_public(a: argparse.Namespace) -> int:
    """Run one catalog entry's public benchmark against `--model`, append a
    spend record to `--results`/ledger.jsonl, and write the summary to
    `--results`.

    The ledger line is written before the summary, and its `run_id` is the
    suite name and the run's `started_at` rather than the summary filename,
    so a live run's spend is recorded even if writing the summary fails.

    `--no-cost-cap` and `--full` pass through to `run_public` unchanged
    (see its docstring for the ValueError this combination can raise).
    `--temperature`, `--max-tokens`, and `--extra-body` (parsed as JSON)
    build the `generate` dict passed to `run_public`; only the options
    actually given are included. `--model-args` (parsed as a JSON object,
    e.g. `{"device": "cuda:0", "dtype": "bfloat16"}` for Inspect's
    `hf/` provider) passes through to `run_public` as `model_args`.
    `--task-args` (parsed as a JSON object, e.g.
    `{"with_sandbox_tasks": "no"}` for `inspect_evals/agentdojo`) passes
    through to `run_public` as `task_args`, keyword arguments for the
    Inspect task function itself rather than the model. After the success
    line, every metric whose name contains "strict" or "loose" (IFEval's
    per-dimension accuracy metrics) prints on its own line, four decimals,
    so a calibration run's full metric set is visible without opening the
    summary file.

    Returns 2 if `entry` is not in the catalog, if `--extra-body` is not
    valid JSON, if `--model-args` or `--task-args` is not a JSON object, if
    the entry is not runnable through Inspect, if `--model` has no cost
    data Inspect can use, or if the run exceeds `--budget-usd`/`--max-wall-s`;
    the message goes to stderr in each case, with no traceback. Returns 0
    on a completed run.

    An Inspect run that comes back with `result.meta["status"] != "success"`
    (e.g. a provider ran out of credits mid-run) is a record, not a
    measurement, and is handled on its own path: the ledger still gets a
    line (the run may have spent money before it failed), and the per-run
    summary is still written for the record, but `latest.json` is
    deliberately left alone (`write_summary(..., promote_latest=False)`),
    since promoting it would let an errored run pass or fail the gate in
    place of the last real measurement. This prints "run failed: ..." and
    the per-run file's path to stderr and returns 2, without reaching the
    success-path printout below.
    """
    entries = {e.id: e for e in load_catalog(Path(a.catalog))}
    if a.entry not in entries:
        print(f"no catalog entry {a.entry}", file=sys.stderr)
        return 2
    try:
        generate, model_args, task_args = _parse_public_options(a)
    except _CliOptionError as e:
        print(str(e), file=sys.stderr)
        return 2
    budget = Budget(max_usd=a.budget_usd, max_wall_s=a.max_wall_s)
    try:
        result = run_public(
            entries[a.entry],
            model=a.model,
            limit=a.limit,
            budget=budget,
            log_dir=Path(a.log_dir),
            task_args=task_args,
            no_cost_cap=a.no_cost_cap,
            full=a.full,
            generate=generate,
            model_args=model_args,
        )
    except (BudgetExceeded, ValueError) as e:
        print(str(e), file=sys.stderr)
        return 2
    results_dir = Path(a.results)
    if result.meta.get("status") != "success":
        message = str(result.meta.get("error", result.meta.get("status", "unknown")))
        Ledger(results_dir / "ledger.jsonl").record(
            run_id=f"{result.suite}-{result.started_at}",
            suite=result.suite,
            target=a.model,
            usd=result.metrics["usd"],
            note=f"error: {message[:80]}",
        )
        path = write_summary(result, results_dir, promote_latest=False)
        print(f"run failed: {result.suite} on {a.model}: {message}", file=sys.stderr)
        print(f"per-run file: {path}", file=sys.stderr)
        return 2
    # Ledger first: the money is already spent by the time run_public returns,
    # so the spend record must not depend on the summary write succeeding.
    Ledger(results_dir / "ledger.jsonl").record(
        run_id=f"{result.suite}-{result.started_at}",
        suite=result.suite,
        target=a.model,
        usd=result.metrics["usd"],
        note=f"limit={a.limit}",
    )
    path = write_summary(result, results_dir)
    accuracy = result.metrics["accuracy"]
    samples = int(result.metrics["samples_total"])
    usd = result.metrics["usd"]
    summary = f"{result.suite} on {a.model}: accuracy {accuracy:.4f} over {samples} samples"
    print(f"{summary}, ${usd:.4f} -> {path}")
    for name, value in sorted(result.metrics.items()):
        if "strict" in name or "loose" in name:
            print(f"  {name}: {value:.4f}")
    return 0


def cmd_run_mcp(a: argparse.Namespace) -> int:
    """Run every case under `--suite-dir` against an MCP server, driven by
    an Inspect ReAct agent on `--model`, and write the summary to
    `--results`.

    The server is either remote (`--mcp-url`, with `--mcp-authorization`
    for a bearer token) or a local child process (`--mcp-command` plus any
    `--mcp-args`); argparse requires exactly one of the two. `--max-steps`
    is the target's own ceiling on agent steps, which bounds each case's
    own `max_steps`. `--model-args` is a JSON object of Inspect model
    constructor keyword arguments. `--server-name` names the target
    explicitly, as `mcp:<name>`; without it a stdio server is named after
    its executable plus a hash of its command line, and an HTTP server
    after its URL.

    The server is contacted once before the suite runs, through
    `list_tools()`, so an unreachable server costs one connection attempt
    rather than one failed case for every case in the suite. The tool names
    it reports are printed and recorded in the summary's
    `meta["mcp_tools"]`, as the record of what the agent could reach.

    Returns 2 if `--model-args` is not a JSON object or if the server
    cannot be reached; 0 otherwise, however many cases failed, matching
    `run offline` (the gate, not this command, decides pass/fail for CI).
    Prints the pass count and each failing case's reason.
    """
    try:
        model_args = _model_args(a)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"invalid --model-args JSON: {e}", file=sys.stderr)
        return 2
    common: dict[str, Any] = {
        "model": a.model,
        "max_steps": a.max_steps,
        "model_args": model_args,
        "log_dir": Path(a.log_dir) if a.log_dir else None,
        "server_name": a.server_name,
    }
    try:
        if a.mcp_url:
            target = MCPTarget.http(url=a.mcp_url, authorization=a.mcp_authorization, **common)
        else:
            target = MCPTarget.stdio(command=a.mcp_command, args=a.mcp_args or [], **common)
        tools = target.list_tools()
    except TargetUnavailable as e:
        print(f"target unavailable: {e}", file=sys.stderr)
        return 2
    print(f"{target.name}: {len(tools)} tools ({', '.join(tools)})")
    suite_dir = Path(a.suite_dir)
    result = run_suite(
        suite_dir.name,
        load_cases(suite_dir),
        target,
        budget=Budget(max_usd=a.budget_usd, max_wall_s=a.max_wall_s),
    )
    result.meta["mcp_tools"] = tools
    path = write_summary(result, Path(a.results))
    passed = int(result.metrics["cases_passed"])
    total = int(result.metrics["cases_total"])
    print(f"{result.suite}: {passed}/{total} passed -> {path}")
    for c in result.cases:
        if not c.passed:
            why = c.skipped_reason or "; ".join(g.explanation for g in c.grades if not g.passed)
            print(f"  FAIL {c.name}: {why}")
    return 0


def _current_for(config_suites: list[str], results: Path) -> dict[str, dict[str, Any]]:
    """Find each configured suite's latest summary under `results`.

    A gate suite name like "offline_core_cost" may not have its own
    results directory; this tries the full name first, then each shorter
    prefix ending right before an underscore ("offline_core", ...), and
    keeps the first one that actually has a `latest.json`. A suite with no
    matching directory at all is simply absent from the returned mapping.
    """
    out: dict[str, dict[str, Any]] = {}
    for name in config_suites:
        candidates = [name] + [name[:i] for i in range(len(name) - 1, 0, -1) if name[i] == "_"]
        for c in candidates:
            s = latest_summary(results, c)
            if s is not None:
                out[name] = s
                break
    return out


def cmd_gate(a: argparse.Namespace) -> int:
    """Compare the latest results against `--config`'s thresholds and
    either print a pass/fail markdown report (writing `--junit` and
    `--markdown` copies when given), or, with `--update-baseline`, copy
    each current summary's metrics into `--baseline` instead of judging
    anything.

    A written baseline also carries the summary's `target` (the model or
    target name the run measured), so a later gate run can tell whether
    the current run was measured on the same target as the baseline; see
    `gate.compare.compare`.

    Returns 0 when every threshold passes (or after updating baselines);
    returns 1 when any threshold fails or is unstable.
    """
    config = load_gate_config(Path(a.config))
    results, baselines = Path(a.results), Path(a.baseline)
    current = _current_for(list(config.suites), results)
    if a.update_baseline:
        baselines.mkdir(parents=True, exist_ok=True)
        for name, summary in current.items():
            payload = {
                "suite": name,
                "target": summary.get("target"),
                "metrics": summary["metrics"],
                "from": summary.get("started_at"),
            }
            text = json.dumps(payload, indent=2) + "\n"
            (baselines / f"{name}.json").write_text(text, encoding="utf-8")
        print(f"updated {len(current)} baselines in {baselines}")
        return 0
    baseline = {
        name: read_summary(baselines / f"{name}.json")
        for name in config.suites
        if (baselines / f"{name}.json").exists()
    }
    report = compare(config, baseline, current)
    md = to_markdown(report)
    print(md)
    if a.junit:
        Path(a.junit).parent.mkdir(parents=True, exist_ok=True)
        Path(a.junit).write_text(to_junit(report), encoding="utf-8")
    if a.markdown:
        Path(a.markdown).parent.mkdir(parents=True, exist_ok=True)
        Path(a.markdown).write_text(md, encoding="utf-8")
    return 0 if report.passed else 1


def cmd_report(a: argparse.Namespace) -> int:
    """Render every suite's latest summary under `--results` into one HTML
    report at `--out`, including `--gate-markdown`'s content when that
    file exists. Always returns 0.
    """
    results = Path(a.results)
    summaries = [read_summary(p) for p in sorted(results.glob("*/latest.json"))]
    gate_md = None
    if a.gate_markdown and Path(a.gate_markdown).exists():
        gate_md = Path(a.gate_markdown).read_text(encoding="utf-8")
    html = render_html(
        summaries,
        gate_markdown=gate_md,
        ledger_total_usd=Ledger(results / "ledger.jsonl").total_usd(),
    )
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(html, encoding="utf-8")
    print(f"wrote {a.out} ({len(summaries)} suites)")
    return 0


def _add_run_mcp(run: argparse._SubParsersAction) -> None:
    """Wire the `run mcp` subcommand onto the `run` subparser group.

    Split out of `build_parser` so that function stays under the statement
    ceiling the linter enforces. `--mcp-url` and `--mcp-command` are a
    required mutually exclusive group: a run needs exactly one server, and
    argparse rejects zero or both before any command code runs.
    """
    mcp = run.add_parser("mcp")
    mcp.add_argument("--suite-dir", required=True)
    where = mcp.add_mutually_exclusive_group(required=True)
    where.add_argument("--mcp-url", help="URL of a remote MCP server (streamable HTTP).")
    where.add_argument("--mcp-command", help="Executable that runs a local MCP server on stdio.")
    mcp.add_argument("--mcp-args", nargs="*", help="Arguments for --mcp-command.")
    mcp.add_argument("--mcp-authorization", help="OAuth bearer token for --mcp-url.")
    mcp.add_argument(
        "--server-name",
        help="Name this target mcp:<name>, instead of deriving one from the command line or URL.",
    )
    mcp.add_argument("--model", required=True)
    mcp.add_argument(
        "--model-args",
        help="JSON object of Inspect model constructor kwargs (e.g. device, "
        "dtype for the hf/ provider).",
    )
    mcp.add_argument("--results", default="results")
    mcp.add_argument("--log-dir", help="Where Inspect writes its .eval logs (default: temporary).")
    mcp.add_argument("--max-steps", type=int, default=8)
    mcp.add_argument("--budget-usd", type=float, default=5.0)
    mcp.add_argument("--max-wall-s", type=float, default=1800.0)
    mcp.set_defaults(fn=cmd_run_mcp)


def build_parser() -> argparse.ArgumentParser:
    """Assemble the `evalplat` argument parser: `catalog list`,
    `run offline`, `run public`, `run mcp`, `gate`, and `report`, each
    wired to its `cmd_*` function via `set_defaults(fn=...)`.
    """
    p = argparse.ArgumentParser(prog="evalplat")
    sub = p.add_subparsers(dest="cmd", required=True)

    cat = sub.add_parser("catalog").add_subparsers(dest="sub", required=True).add_parser("list")
    cat.add_argument("--catalog", default="catalog/entries")
    cat.add_argument("--category")
    cat.add_argument("--status")
    cat.add_argument("--runnable", action="store_true")
    cat.set_defaults(fn=cmd_catalog)

    run = sub.add_parser("run").add_subparsers(dest="sub", required=True)
    off = run.add_parser("offline")
    off.add_argument("--suite-dir", required=True)
    off.add_argument(
        "--target",
        default="scripted",
        choices=["scripted", "agent-platform-local", "agent-platform-http"],
    )
    off.add_argument("--base-url")
    off.add_argument("--results", default="results")
    off.add_argument("--budget-usd", type=float, default=0.0)
    off.add_argument("--max-wall-s", type=float, default=600.0)
    off.set_defaults(fn=cmd_run_offline)
    pub = run.add_parser("public")
    pub.add_argument("entry")
    pub.add_argument("--model", required=True)
    pub.add_argument("--limit", type=int)
    pub.add_argument("--budget-usd", type=float, default=5.0)
    pub.add_argument("--max-wall-s", type=float, default=3600.0)
    pub.add_argument("--results", default="results")
    pub.add_argument("--log-dir", default="logs")
    pub.add_argument("--catalog", default="catalog/entries")
    pub.add_argument(
        "--no-cost-cap",
        action="store_true",
        help="Do not pass a cost cap to Inspect (for models it cannot price, "
        "e.g. HF Inference Providers); requires --limit or --full.",
    )
    pub.add_argument(
        "--full",
        action="store_true",
        help="Allow --no-cost-cap with no --limit: run the full dataset.",
    )
    pub.add_argument("--temperature", type=float)
    pub.add_argument("--max-tokens", type=int)
    pub.add_argument("--extra-body", help="JSON object forwarded as Inspect's extra_body.")
    pub.add_argument(
        "--model-args",
        help="JSON object of Inspect model constructor kwargs (e.g. device, "
        "dtype for the hf/ provider).",
    )
    pub.add_argument(
        "--task-args",
        help="JSON object of keyword arguments for the Inspect task function "
        "itself (e.g. with_sandbox_tasks for inspect_evals/agentdojo).",
    )
    pub.set_defaults(fn=cmd_run_public)

    _add_run_mcp(run)

    gate = sub.add_parser("gate")
    gate.add_argument("--config", default="gate.yaml")
    gate.add_argument("--baseline", default="baselines")
    gate.add_argument("--results", default="results")
    gate.add_argument("--junit")
    gate.add_argument("--markdown")
    gate.add_argument("--update-baseline", action="store_true")
    gate.set_defaults(fn=cmd_gate)

    rep = sub.add_parser("report")
    rep.add_argument("--results", default="results")
    rep.add_argument("--out", default="out/report.html")
    rep.add_argument("--gate-markdown")
    rep.set_defaults(fn=cmd_report)
    return p


def main(argv: list[str] | None = None) -> int:
    """Parse `argv` (or `sys.argv` when None) and run the selected
    subcommand, returning its exit code.
    """
    args = build_parser().parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    sys.exit(main())
