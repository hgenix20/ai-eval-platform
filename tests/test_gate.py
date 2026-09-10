import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from eval_platform.gate import (
    GateConfig,
    GateReport,
    MetricVerdict,
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


def test_junit_escapes_attribute_values_as_well_formed_xml():
    # A detail with a quote and an angle bracket would break naive f-string
    # interpolation into an attribute; quoteattr must handle both.
    report = GateReport(
        verdicts=(
            MetricVerdict(
                suite="offline_core",
                metric="pass_rate",
                baseline=None,
                current=0.5,
                threshold="min=1.0",
                verdict="fail",
                detail='cur 0.5 < min 1.0, saw "bad" <output>',
            ),
        )
    )
    xml_text = to_junit(report)
    root = ET.fromstring(xml_text)
    failure = root.find("testcase/failure")
    assert failure is not None
    assert failure.get("message") == 'cur 0.5 < min 1.0, saw "bad" <output>'


def test_markdown_escapes_pipes_and_keeps_seven_cells():
    report = GateReport(
        verdicts=(
            MetricVerdict(
                suite="offline_core",
                metric="pass_rate",
                baseline=None,
                current=0.5,
                threshold="min=1.0",
                verdict="fail",
                detail="a|b",
            ),
        )
    )
    md = to_markdown(report)
    row = next(line for line in md.splitlines() if line.startswith("| offline_core"))
    assert "a\\|b" in row
    # Split on "|" that is not escaped by a preceding backslash, the way a
    # markdown table parser would; a bare "|" in a cell would otherwise
    # split it into extra columns.
    segments = re.split(r"(?<!\\)\|", row)
    cells = [c.strip() for c in segments if c.strip() != ""]
    assert len(cells) == 7
    assert cells[-1] == "a\\|b"


def test_max_increase_pct_against_zero_baseline_is_not_measured_when_current_rises():
    cfg = GateConfig(suites={"cost": Threshold(metric="usd_per_run_p50", max_increase_pct=10)})
    base = _cur(cost={"usd_per_run_p50": 0.0})
    r = compare(cfg, base, _cur(cost={"usd_per_run_p50": 0.01}))
    v = r.verdicts[0]
    assert v.verdict == "not_measured"
    assert v.detail == "baseline is zero; percentage increase undefined"


def test_max_increase_pct_against_zero_baseline_passes_when_current_is_also_zero():
    cfg = GateConfig(suites={"cost": Threshold(metric="usd_per_run_p50", max_increase_pct=10)})
    base = _cur(cost={"usd_per_run_p50": 0.0})
    r = compare(cfg, base, _cur(cost={"usd_per_run_p50": 0.0}))
    assert r.verdicts[0].verdict == "pass"


def test_non_numeric_metric_value_raises_value_error():
    cfg = GateConfig(suites={"offline_core": Threshold(metric="pass_rate", min=1.0)})
    with pytest.raises(ValueError, match=re.escape("offline_core.pass_rate")):
        compare(cfg, {}, _cur(offline_core={"pass_rate": "not-a-number"}))


def test_errored_run_status_is_not_measured_regardless_of_metric_value():
    """A summary whose meta["status"] is present and not "success" (an
    errored Inspect run) must never pass or fail its row: it is treated
    as not measured even though the metric value itself would otherwise
    read as a clean failure."""
    cfg = GateConfig(suites={"public_ifeval": Threshold(metric="accuracy", min=0.70)})
    current = {"public_ifeval": {"metrics": {"accuracy": 0.0}, "meta": {"status": "error"}}}
    r = compare(cfg, {}, current)
    v = r.verdicts[0]
    assert v.verdict == "not_measured"
    assert v.detail == "latest run errored"


def test_success_status_does_not_trigger_the_errored_run_check():
    cfg = GateConfig(suites={"public_ifeval": Threshold(metric="accuracy", min=0.70)})
    current = {"public_ifeval": {"metrics": {"accuracy": 0.9}, "meta": {"status": "success"}}}
    r = compare(cfg, {}, current)
    assert r.verdicts[0].verdict == "pass"


def test_not_measured_detail_distinguishes_unrun_suite_from_missing_metric():
    r = compare(CFG, {}, _cur(offline_core={"pass_rate": 1.0}, trajectory={"other_metric": 1.0}))
    v = {x.suite: x for x in r.verdicts}
    assert v["cost"].detail == "suite not run"  # absent from current entirely
    assert v["trajectory"].detail == "metric absent from summary"  # present, wrong metric


def test_target_mismatch_is_not_measured_for_relative_only_threshold():
    cfg = GateConfig(suites={"trajectory": Threshold(metric="pass_rate", max_drop=0.02)})
    base = {"trajectory": {"metrics": {"pass_rate": 1.0}, "target": "model-a"}}
    current = {"trajectory": {"metrics": {"pass_rate": 0.5}, "target": "model-b"}}
    r = compare(cfg, base, current)
    v = r.verdicts[0]
    assert v.verdict == "not_measured"
    assert v.detail == "target differs from baseline (model-a vs model-b)"
    assert r.passed


def test_target_mismatch_still_fails_a_failed_absolute_check():
    cfg = GateConfig(suites={"trajectory": Threshold(metric="pass_rate", min=0.95, max_drop=0.02)})
    base = {"trajectory": {"metrics": {"pass_rate": 1.0}, "target": "model-a"}}
    current = {"trajectory": {"metrics": {"pass_rate": 0.5}, "target": "model-b"}}
    r = compare(cfg, base, current)
    v = r.verdicts[0]
    assert v.verdict == "fail"
    assert "min" in v.detail
    assert not r.passed


def test_same_target_is_unaffected_by_the_target_check():
    cfg = GateConfig(suites={"trajectory": Threshold(metric="pass_rate", max_drop=0.02)})
    base = {"trajectory": {"metrics": {"pass_rate": 1.0}, "target": "model-a"}}
    current = {"trajectory": {"metrics": {"pass_rate": 0.99}, "target": "model-a"}}
    r = compare(cfg, base, current)
    v = r.verdicts[0]
    assert v.verdict == "pass"
    assert v.detail == "within thresholds"
