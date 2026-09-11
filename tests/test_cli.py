import json
from pathlib import Path

from inspect_ai import Task
from inspect_ai import eval as inspect_eval
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.model import ModelOutput
from inspect_ai.scorer import match

import eval_platform.cli as cli_mod
from eval_platform.budget import BudgetExceeded
from eval_platform.cli import main
from eval_platform.suites import eval_log_to_suite_result
from eval_platform.targets import TargetUnavailable
from eval_platform.types import SuiteResult

ROOT = Path(__file__).resolve().parents[1]

CASE = """
name: scripted-ok
goal: g
target_requirements: [scripted]
script:
  - {kind: tool, name: lookup, output: v, cost_usd: 0.0, latency_ms: 1}
  - {kind: model, name: final, status: completed, answer: done}
expect: {status: completed}
"""


def test_catalog_list_prints_rows(capsys):
    assert (
        main(
            [
                "catalog",
                "list",
                "--category",
                "safety",
                "--catalog",
                str(ROOT / "catalog" / "entries"),
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "harmbench" in out and "gpqa-diamond" not in out


def test_run_offline_then_gate_then_report(tmp_path: Path):
    suite = tmp_path / "suites" / "offline_core"
    suite.mkdir(parents=True)
    (suite / "a.yaml").write_text(CASE, encoding="utf-8")
    results = tmp_path / "results"
    cfg = tmp_path / "gate.yaml"
    cfg.write_text(
        "suites:\n"
        "  offline_core: {metric: pass_rate, min: 1.0}\n"
        "  offline_core_cost: {metric: usd_per_run_p50, max_increase_pct: 10}\n",
        encoding="utf-8",
    )
    baselines = tmp_path / "baselines"

    assert (
        main(
            [
                "run",
                "offline",
                "--suite-dir",
                str(suite),
                "--target",
                "scripted",
                "--results",
                str(results),
            ]
        )
        == 0
    )
    assert (results / "offline_core" / "latest.json").exists()

    junit, md = tmp_path / "junit.xml", tmp_path / "gate.md"
    assert (
        main(
            [
                "gate",
                "--config",
                str(cfg),
                "--baseline",
                str(baselines),
                "--results",
                str(results),
                "--junit",
                str(junit),
                "--markdown",
                str(md),
            ]
        )
        == 0
    )
    assert "<testsuite" in junit.read_text() and "| offline_core | pass_rate |" in md.read_text()

    assert (
        main(
            [
                "gate",
                "--config",
                str(cfg),
                "--baseline",
                str(baselines),
                "--results",
                str(results),
                "--update-baseline",
            ]
        )
        == 0
    )
    baseline_payload = json.loads((baselines / "offline_core.json").read_text())
    assert baseline_payload["metrics"]["pass_rate"] == 1.0
    assert baseline_payload["target"] == "scripted"

    out = tmp_path / "report.html"
    assert (
        main(["report", "--results", str(results), "--out", str(out), "--gate-markdown", str(md)])
        == 0
    )
    assert "offline_core" in out.read_text(encoding="utf-8")


def test_gate_fails_on_threshold(tmp_path: Path):
    suite = (
        tmp_path / "offline_core"
    )  # the suite name is the directory name and must match gate.yaml
    suite.mkdir()
    (suite / "a.yaml").write_text(
        CASE.replace("expect: {status: completed}", "expect: {status: failed}"), encoding="utf-8"
    )
    results = tmp_path / "results"
    cfg = tmp_path / "gate.yaml"
    cfg.write_text("suites:\n  offline_core: {metric: pass_rate, min: 1.0}\n", encoding="utf-8")
    main(
        [
            "run",
            "offline",
            "--suite-dir",
            str(suite),
            "--target",
            "scripted",
            "--results",
            str(results),
        ]
    )
    assert (
        main(
            [
                "gate",
                "--config",
                str(cfg),
                "--baseline",
                str(tmp_path / "b"),
                "--results",
                str(results),
            ]
        )
        == 1
    )


def test_run_offline_unavailable_target_exits_2(tmp_path: Path, monkeypatch, capsys):
    """An agent-platform-http target that cannot be reached makes `run
    offline` exit 2 and print "target unavailable" to stderr, without
    running any case. The constructor is stubbed rather than pointed at a
    real closed port, so this test is not sensitive to how fast (or slow)
    this machine's TCP stack refuses a connection.
    """
    suite = tmp_path / "suites" / "offline_core"
    suite.mkdir(parents=True)
    (suite / "a.yaml").write_text(CASE, encoding="utf-8")
    results = tmp_path / "results"

    class _UnreachableHttpTarget:
        def __init__(self, base_url: str) -> None:
            raise TargetUnavailable(f"agent platform not reachable at {base_url}")

    monkeypatch.setattr(cli_mod, "AgentPlatformHttpTarget", _UnreachableHttpTarget)

    rc = main(
        [
            "run",
            "offline",
            "--suite-dir",
            str(suite),
            "--target",
            "agent-platform-http",
            "--base-url",
            "http://127.0.0.1:9",
            "--results",
            str(results),
        ]
    )
    assert rc == 2
    assert "target unavailable" in capsys.readouterr().err


def test_run_public_unknown_entry_exits_2(tmp_path: Path, capsys):
    """`run public` on an id absent from the catalog exits 2 and names the
    problem on stderr, without attempting a benchmark run."""
    results = tmp_path / "results"
    rc = main(
        [
            "run",
            "public",
            "no-such-benchmark",
            "--model",
            "mockllm/model",
            "--catalog",
            str(ROOT / "catalog" / "entries"),
            "--results",
            str(results),
        ]
    )
    assert rc == 2
    assert "no catalog entry" in capsys.readouterr().err


def test_run_public_budget_exceeded_exits_2(tmp_path: Path, monkeypatch, capsys):
    """A BudgetExceeded raised mid-run makes `run public` exit 2, print the
    reason to stderr, and write nothing to the ledger: a run that never
    produced a SuiteResult has nothing to record."""
    results = tmp_path / "results"

    def _raise_budget_exceeded(*args, **kwargs):
        raise BudgetExceeded("usd", "no budget remaining")

    monkeypatch.setattr(cli_mod, "run_public", _raise_budget_exceeded)

    rc = main(
        [
            "run",
            "public",
            "ifeval",
            "--model",
            "mockllm/model",
            "--catalog",
            str(ROOT / "catalog" / "entries"),
            "--results",
            str(results),
        ]
    )
    assert rc == 2
    assert "budget" in capsys.readouterr().err
    assert not (results / "ledger.jsonl").exists()


def test_run_public_value_error_exits_2(tmp_path: Path, monkeypatch, capsys):
    """A ValueError raised for an unrunnable entry or an uncosted model
    makes `run public` exit 2 and print the reason to stderr, not a
    traceback."""
    results = tmp_path / "results"

    def _raise_value_error(*args, **kwargs):
        raise ValueError("model x has no cost data")

    monkeypatch.setattr(cli_mod, "run_public", _raise_value_error)

    rc = main(
        [
            "run",
            "public",
            "ifeval",
            "--model",
            "mockllm/model",
            "--catalog",
            str(ROOT / "catalog" / "entries"),
            "--results",
            str(results),
        ]
    )
    assert rc == 2
    assert "no cost data" in capsys.readouterr().err


def _errored_public_result(suite="public_ifeval", target="mockllm/model"):
    """A SuiteResult shaped like `run_public`'s output for a run Inspect
    stopped with a provider error: no scored samples, meta status "error"."""
    return SuiteResult(
        suite=suite,
        target=target,
        started_at="2026-09-10T00:00:00+00:00",
        finished_at="2026-09-10T00:00:05+00:00",
        cases=(),
        metrics={
            "accuracy": 0.0,
            "samples_total": 25.0,
            "samples_completed": 0.0,
            "input_tokens": 0.0,
            "output_tokens": 0.0,
            "usd": 0.0,
            "samples_unscored": 0.0,
            "samples_errored": 25.0,
        },
        meta={"status": "error", "error": "Error code: 402 - credits depleted"},
    )


def test_run_public_errored_run_exits_2_and_does_not_promote_latest(
    tmp_path: Path, monkeypatch, capsys
):
    """When `run_public` returns a SuiteResult whose meta status is not
    "success" (Inspect stopped the run on a provider error), `run public`
    must exit 2, print "run failed" with the error message to stderr,
    leave latest.json untouched (absent here, since none existed yet),
    and still record a ledger line noting the error so the spend is not
    lost."""
    results = tmp_path / "results"
    monkeypatch.setattr(cli_mod, "run_public", lambda *a, **kw: _errored_public_result())

    rc = main(
        [
            "run",
            "public",
            "ifeval",
            "--model",
            "mockllm/model",
            "--catalog",
            str(ROOT / "catalog" / "entries"),
            "--results",
            str(results),
        ]
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "run failed: public_ifeval on mockllm/model" in err
    assert "Error code: 402 - credits depleted" in err
    assert not (results / "public_ifeval" / "latest.json").exists()
    ledger_lines = (results / "ledger.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(ledger_lines) == 1
    ledger_entry = json.loads(ledger_lines[0])
    assert ledger_entry["suite"] == "public_ifeval"
    assert "error" in ledger_entry["note"]


def test_run_public_passes_no_cost_cap_and_generate_options(tmp_path: Path, monkeypatch, capsys):
    """--no-cost-cap, --temperature, --max-tokens, and --extra-body reach
    run_public as no_cost_cap=True and a generate dict built only from the
    options given."""
    results = tmp_path / "results"
    received: dict = {}

    def fake_run_public(entry, **kwargs):
        received.update(kwargs)
        return eval_log_to_suite_result(
            _mock_log(tmp_path), suite="public_ifeval", target=kwargs["model"]
        )

    monkeypatch.setattr(cli_mod, "run_public", fake_run_public)

    rc = main(
        [
            "run",
            "public",
            "ifeval",
            "--model",
            "hf-inference-providers/meta-llama/Llama-3.1-8B-Instruct:deepinfra",
            "--no-cost-cap",
            "--limit",
            "5",
            "--temperature",
            "0",
            "--max-tokens",
            "1024",
            "--extra-body",
            '{"chat_template_kwargs": {"enable_thinking": false}}',
            "--catalog",
            str(ROOT / "catalog" / "entries"),
            "--results",
            str(results),
        ]
    )
    assert rc == 0
    assert received["no_cost_cap"] is True
    assert received["limit"] == 5
    assert received["generate"] == {
        "temperature": 0.0,
        "max_tokens": 1024,
        "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
    }


def test_run_public_passes_model_args(tmp_path: Path, monkeypatch, capsys):
    """--model-args reaches run_public as a parsed dict, for Inspect's `hf/`
    provider (e.g. `device`, `torch_dtype` for a locally loaded model)."""
    results = tmp_path / "results"
    received: dict = {}

    def fake_run_public(entry, **kwargs):
        received.update(kwargs)
        return eval_log_to_suite_result(
            _mock_log(tmp_path), suite="public_ifeval", target=kwargs["model"]
        )

    monkeypatch.setattr(cli_mod, "run_public", fake_run_public)

    rc = main(
        [
            "run",
            "public",
            "ifeval",
            "--model",
            "hf/Qwen/Qwen2.5-3B-Instruct",
            "--model-args",
            '{"device": "cuda:0", "torch_dtype": "bfloat16"}',
            "--catalog",
            str(ROOT / "catalog" / "entries"),
            "--results",
            str(results),
        ]
    )
    assert rc == 0
    assert received["model_args"] == {"device": "cuda:0", "torch_dtype": "bfloat16"}


def test_run_public_passes_task_args(tmp_path: Path, monkeypatch, capsys):
    """--task-args reaches run_public as a parsed dict, for an Inspect task
    function's own keyword arguments (e.g. with_sandbox_tasks for
    inspect_evals/agentdojo, distinct from --model-args)."""
    results = tmp_path / "results"
    received: dict = {}

    def fake_run_public(entry, **kwargs):
        received.update(kwargs)
        return eval_log_to_suite_result(
            _mock_log(tmp_path), suite="public_ifeval", target=kwargs["model"]
        )

    monkeypatch.setattr(cli_mod, "run_public", fake_run_public)

    rc = main(
        [
            "run",
            "public",
            "ifeval",
            "--model",
            "hf/Qwen/Qwen2.5-3B-Instruct",
            "--task-args",
            '{"with_sandbox_tasks": "no"}',
            "--catalog",
            str(ROOT / "catalog" / "entries"),
            "--results",
            str(results),
        ]
    )
    assert rc == 0
    assert received["task_args"] == {"with_sandbox_tasks": "no"}


def test_run_public_bad_task_args_json_exits_2(tmp_path: Path, monkeypatch, capsys):
    """A --task-args value that parses as JSON but is not a JSON object
    (e.g. a list) exits 2 with a message on stderr, before run_public (and
    any spend) is attempted."""
    results = tmp_path / "results"

    def fake_run_public(*args, **kwargs):
        raise AssertionError("run_public must not be called on non-object --task-args")

    monkeypatch.setattr(cli_mod, "run_public", fake_run_public)

    rc = main(
        [
            "run",
            "public",
            "ifeval",
            "--model",
            "hf/Qwen/Qwen2.5-3B-Instruct",
            "--task-args",
            "[1]",
            "--catalog",
            str(ROOT / "catalog" / "entries"),
            "--results",
            str(results),
        ]
    )
    assert rc == 2
    assert capsys.readouterr().err.strip() != ""


def test_run_public_bad_model_args_json_exits_2(tmp_path: Path, monkeypatch, capsys):
    """A --model-args value that parses as JSON but is not a JSON object
    (e.g. a list) exits 2 with a message on stderr, before run_public (and
    any spend) is attempted."""
    results = tmp_path / "results"

    def fake_run_public(*args, **kwargs):
        raise AssertionError("run_public must not be called on non-object --model-args")

    monkeypatch.setattr(cli_mod, "run_public", fake_run_public)

    rc = main(
        [
            "run",
            "public",
            "ifeval",
            "--model",
            "hf/Qwen/Qwen2.5-3B-Instruct",
            "--model-args",
            "[1]",
            "--catalog",
            str(ROOT / "catalog" / "entries"),
            "--results",
            str(results),
        ]
    )
    assert rc == 2
    assert capsys.readouterr().err.strip() != ""


def test_run_public_bad_extra_body_json_exits_2(tmp_path: Path, monkeypatch, capsys):
    """A malformed --extra-body value exits 2 with a message on stderr,
    before run_public (and any spend) is attempted."""
    results = tmp_path / "results"

    def fake_run_public(*args, **kwargs):
        raise AssertionError("run_public must not be called on bad JSON")

    monkeypatch.setattr(cli_mod, "run_public", fake_run_public)

    rc = main(
        [
            "run",
            "public",
            "ifeval",
            "--model",
            "mockllm/model",
            "--extra-body",
            "{not json",
            "--catalog",
            str(ROOT / "catalog" / "entries"),
            "--results",
            str(results),
        ]
    )
    assert rc == 2
    assert capsys.readouterr().err.strip() != ""


def test_run_public_prints_strict_and_loose_metrics(tmp_path: Path, monkeypatch, capsys):
    """The success line is followed by every metrics key containing
    "strict" or "loose", one per line, four decimals."""
    results = tmp_path / "results"
    log = _mock_log(tmp_path)
    result = eval_log_to_suite_result(log, suite="public_ifeval", target="mockllm/model")
    result.metrics["prompt_level_strict_accuracy"] = 0.83
    result.metrics["instruction_level_loose_accuracy"] = 0.912345

    monkeypatch.setattr(cli_mod, "run_public", lambda *a, **kw: result)

    rc = main(
        [
            "run",
            "public",
            "ifeval",
            "--model",
            "mockllm/model",
            "--catalog",
            str(ROOT / "catalog" / "entries"),
            "--results",
            str(results),
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "prompt_level_strict_accuracy: 0.8300" in out
    assert "instruction_level_loose_accuracy: 0.9123" in out


def _mock_log(tmp_path: Path):
    [log] = inspect_eval(
        Task(
            dataset=MemoryDataset(
                [Sample(input="2+2?", target="4"), Sample(input="3+3?", target="6")]
            ),
            scorer=match(),
        ),
        model="mockllm/model",
        model_args={
            "custom_outputs": [
                ModelOutput.from_content(model="mockllm", content="4"),
                ModelOutput.from_content(model="mockllm", content="6"),
            ]
        },
        log_dir=str(tmp_path / "logs"),
        display="none",
    )
    return log


def test_run_public_happy_path_with_mock_model(tmp_path: Path, monkeypatch, capsys):
    """A completed public run writes latest.json under the suite directory
    and exactly one ledger line. `run_public` is monkeypatched to return a
    real SuiteResult built from a mockllm EvalLog, so no network is touched
    and no money is spent, while the CLI's own write path runs for real
    against a target id that carries a provider slash.
    """
    logs, results = tmp_path / "logs", tmp_path / "results"
    [log] = inspect_eval(
        Task(
            dataset=MemoryDataset(
                [Sample(input="2+2?", target="4"), Sample(input="3+3?", target="6")]
            ),
            scorer=match(),
        ),
        model="mockllm/model",
        model_args={
            "custom_outputs": [
                ModelOutput.from_content(model="mockllm", content="4"),
                ModelOutput.from_content(model="mockllm", content="6"),
            ]
        },
        log_dir=str(logs),
        display="none",
    )
    result = eval_log_to_suite_result(log, suite="public_ifeval", target="mockllm/model")
    monkeypatch.setattr(cli_mod, "run_public", lambda *a, **kw: result)

    rc = main(
        [
            "run",
            "public",
            "ifeval",
            "--model",
            "mockllm/model",
            "--limit",
            "2",
            "--catalog",
            str(ROOT / "catalog" / "entries"),
            "--results",
            str(results),
            "--log-dir",
            str(logs),
        ]
    )
    assert rc == 0
    assert (results / "public_ifeval" / "latest.json").exists()
    ledger = (results / "ledger.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(ledger) == 1
    assert json.loads(ledger[0])["suite"] == "public_ifeval"
    assert "public_ifeval on mockllm/model" in capsys.readouterr().out
