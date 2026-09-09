import json
from pathlib import Path

from eval_platform.cli import main

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
    assert json.loads((baselines / "offline_core.json").read_text())["metrics"]["pass_rate"] == 1.0

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
