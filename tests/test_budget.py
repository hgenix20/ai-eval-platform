import json

import pytest

from eval_platform.budget import Budget, BudgetExceeded, Ledger


def test_charge_accumulates_and_raises_past_ceiling():
    b = Budget(max_usd=1.0, max_wall_s=60)
    b.charge(0.4)
    b.charge(0.5)
    assert b.remaining_usd() == pytest.approx(0.1)
    with pytest.raises(BudgetExceeded) as e:
        b.charge(0.2)
    assert e.value.reason == "usd"


def test_check_projects_next_sample():
    b = Budget(max_usd=1.0, max_wall_s=60)
    b.charge(0.9)
    b.check(projected_next_usd=0.05)
    with pytest.raises(BudgetExceeded):
        b.check(projected_next_usd=0.2)


def test_check_raises_on_wall_clock(monkeypatch):
    b = Budget(max_usd=1.0, max_wall_s=10)
    monkeypatch.setattr("eval_platform.budget.time.monotonic", lambda: b.started + 11)
    with pytest.raises(BudgetExceeded) as e:
        b.check()
    assert e.value.reason == "wall"


def test_ledger_appends_lines_and_totals(tmp_path):
    led = Ledger(tmp_path / "ledger.jsonl")
    led.record(run_id="r1", suite="public/ifeval", target="anthropic/x", usd=0.5)
    led.record(run_id="r2", suite="public/ifeval", target="anthropic/x", usd=0.25, note="rerun")
    lines = (tmp_path / "ledger.jsonl").read_text().splitlines()
    assert len(lines) == 2 and json.loads(lines[1])["note"] == "rerun"
    assert led.total_usd() == pytest.approx(0.75)


def test_ledger_total_is_zero_when_missing(tmp_path):
    assert Ledger(tmp_path / "none.jsonl").total_usd() == 0.0


def test_ledger_total_raises_on_malformed_line_with_location(tmp_path):
    path = tmp_path / "ledger.jsonl"
    path.write_text('{"usd": 0.5}\nnot json\n')
    with pytest.raises(ValueError) as e:
        Ledger(path).total_usd()
    assert ":2:" in str(e.value)
