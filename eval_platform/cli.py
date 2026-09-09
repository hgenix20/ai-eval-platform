"""evalplat: catalog, run offline and public, gate, report."""

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


def cmd_run_public(a: argparse.Namespace) -> int:
    """Run one catalog entry's public benchmark against `--model`, append a
    spend record to `--results`/ledger.jsonl, and write the summary to
    `--results`.

    The ledger line is written before the summary, and its `run_id` is the
    suite name and the run's `started_at` rather than the summary filename,
    so a live run's spend is recorded even if writing the summary fails.

    Returns 2 if `entry` is not in the catalog, if it is not runnable
    through Inspect, if `--model` has no cost data Inspect can use, or if
    the run exceeds `--budget-usd`/`--max-wall-s`; the message goes to
    stderr in each case, with no traceback. Returns 0 on a completed run.
    """
    entries = {e.id: e for e in load_catalog(Path(a.catalog))}
    if a.entry not in entries:
        print(f"no catalog entry {a.entry}", file=sys.stderr)
        return 2
    budget = Budget(max_usd=a.budget_usd, max_wall_s=a.max_wall_s)
    try:
        result = run_public(
            entries[a.entry], model=a.model, limit=a.limit, budget=budget, log_dir=Path(a.log_dir)
        )
    except (BudgetExceeded, ValueError) as e:
        print(str(e), file=sys.stderr)
        return 2
    # Ledger first: the money is already spent by the time run_public returns,
    # so the spend record must not depend on the summary write succeeding.
    Ledger(Path(a.results) / "ledger.jsonl").record(
        run_id=f"{result.suite}-{result.started_at}",
        suite=result.suite,
        target=a.model,
        usd=result.metrics["usd"],
        note=f"limit={a.limit}",
    )
    path = write_summary(result, Path(a.results))
    accuracy = result.metrics["accuracy"]
    samples = int(result.metrics["samples_total"])
    usd = result.metrics["usd"]
    summary = f"{result.suite} on {a.model}: accuracy {accuracy:.4f} over {samples} samples"
    print(f"{summary}, ${usd:.4f} -> {path}")
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


def build_parser() -> argparse.ArgumentParser:
    """Assemble the `evalplat` argument parser: `catalog list`,
    `run offline`, `run public`, `gate`, and `report`, each wired to its
    `cmd_*` function via `set_defaults(fn=...)`.
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
    pub.set_defaults(fn=cmd_run_public)

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
