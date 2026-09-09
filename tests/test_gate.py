from pathlib import Path

import pytest

from eval_platform.gate import (
    GateConfig,
    Threshold,
    compare,
    load_gate_config,
    to_junit,
    to_markdown,
)

CFG = GateConfig(
    suites={
        "offline_core": Threshold(metric="pass_rate", min=1.0),
        "trajectory": Threshold(metric="pass_rate", min=0.95, max_drop=0.02),
        "cost": Threshold(metric="usd_per_run_p50", max_increase_pct=10),
        "groundedness": Threshold(metric="unsupported_rate", max=0.05, max_rise=0.02),
    }
)


def _cur(**suites):
    return {k: {"metrics": v} for k, v in suites.items()}


def test_absolute_min_and_max():
    r = compare(
        CFG, {}, _cur(offline_core={"pass_rate": 1.0}, groundedness={"unsupported_rate": 0.06})
    )
    v = {x.suite: x.verdict for x in r.verdicts}
    assert v["offline_core"] == "pass" and v["groundedness"] == "fail" and not r.passed


def test_relative_checks_need_a_baseline():
    r = compare(CFG, {}, _cur(trajectory={"pass_rate": 0.97}, cost={"usd_per_run_p50": 0.5}))
    v = {x.suite: x.verdict for x in r.verdicts}
    assert v["trajectory"] == "pass" and v["cost"] == "not_measured" and r.passed


def test_max_drop_and_increase_pct_against_baseline():
    base = _cur(trajectory={"pass_rate": 1.0}, cost={"usd_per_run_p50": 1.0})
    r = compare(CFG, base, _cur(trajectory={"pass_rate": 0.97}, cost={"usd_per_run_p50": 1.05}))
    assert {x.suite: x.verdict for x in r.verdicts}["trajectory"] == "fail"  # dropped 0.03 > 0.02
    assert {x.suite: x.verdict for x in r.verdicts}["cost"] == "pass"  # +5% <= 10%
    r2 = compare(CFG, base, _cur(trajectory={"pass_rate": 0.99}, cost={"usd_per_run_p50": 1.2}))
    assert {x.suite: x.verdict for x in r2.verdicts}["cost"] == "fail"


def test_missing_suite_is_not_measured_and_does_not_block():
    r = compare(CFG, {}, _cur(offline_core={"pass_rate": 1.0}))
    assert {x.suite: x.verdict for x in r.verdicts}["trajectory"] == "not_measured" and r.passed


def test_junit_and_markdown_render():
    r = compare(CFG, {}, _cur(offline_core={"pass_rate": 0.5}))
    x = to_junit(r)
    assert "<testsuite" in x and "<failure" in x and 'name="offline_core.pass_rate"' in x
    md = to_markdown(r)
    assert "| offline_core | pass_rate |" in md and "fail" in md


def test_load_gate_config_rejects_unknown_keys(tmp_path: Path):
    p = tmp_path / "gate.yaml"
    p.write_text("suites:\n  a: {metric: pass_rate, min: 1, bogus: 2}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_gate_config(p)
