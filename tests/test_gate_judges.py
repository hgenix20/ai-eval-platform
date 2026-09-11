from eval_platform.gate.compare import compare
from eval_platform.gate.config import GateConfig, JudgeRules, Threshold


def _cfg(**judges):
    return GateConfig(
        suites={
            "g": Threshold(metric="judge.faithfulness.hf/x.pass_rate", min=0.5),
            "u": Threshold(metric="unsupported_rate", max_rise=0.02),
        },
        judges=JudgeRules(**judges),
    )


def _cur(pass_rate=0.8, swap=None):
    m = {"judge.faithfulness.hf/x.pass_rate": pass_rate, "unsupported_rate": 0.1}
    if swap is not None:
        m["judge.faithfulness.swap_agreement"] = swap
    return {"g": {"metrics": m, "target": "t"}, "u": {"metrics": m, "target": "t"}}


def _cal(kappa=0.8, swap=0.95):
    return {
        "judges": [{"judge": "faithfulness@1:hf/x", "kappa": kappa}],
        "swap_agreement": swap,
        "kappa_floor": 0.70,
        "min_swap_agreement": 0.90,
        "calibrated": {"faithfulness@1:hf/x": [kappa >= 0.70 and swap >= 0.90, "reason"]},
    }


def test_judge_row_without_calibration_is_not_measured():
    r = compare(_cfg(), {}, _cur(), calibration=None)
    g = next(v for v in r.verdicts if v.suite == "g")
    assert g.verdict == "not_measured" and "uncalibrated" in g.detail


def test_judge_row_uncalibrated_judge_is_not_measured():
    r = compare(_cfg(), {}, _cur(), calibration=_cal(kappa=0.4))
    g = next(v for v in r.verdicts if v.suite == "g")
    assert g.verdict == "not_measured" and "kappa" in g.detail


def test_judge_row_calibrated_judge_is_judged():
    r = compare(_cfg(), {}, _cur(pass_rate=0.3), calibration=_cal())
    g = next(v for v in r.verdicts if v.suite == "g")
    assert g.verdict == "fail"


def test_swap_disagreement_is_unstable():
    r = compare(_cfg(require_swap_agreement=True), {}, _cur(swap=0.6), calibration=_cal())
    g = next(v for v in r.verdicts if v.suite == "g")
    assert g.verdict == "unstable" and not r.passed


def test_non_judge_rows_ignore_calibration():
    r = compare(
        _cfg(),
        {"u": {"metrics": {"unsupported_rate": 0.1}, "target": "t"}},
        _cur(),
        calibration=None,
    )
    u = next(v for v in r.verdicts if v.suite == "u")
    assert u.verdict == "pass"
