import json
from pathlib import Path

import pytest
from inspect_ai.model import ModelOutput, get_model

from eval_platform.calibration import (
    CalibrationItem,
    agreement,
    calibrate,
    cohen_kappa,
    load_items,
    write_report,
)
from eval_platform.cli import main
from eval_platform.graders.judge import RUBRICS, JudgeGrader
from eval_platform.graders.judge_cache import JudgeCache

ROOT = Path(__file__).resolve().parents[1]


def test_kappa_known_values():
    a = ["s", "s", "u", "u", "s", "u", "s", "u"]
    assert cohen_kappa(a, a) == 1.0
    assert cohen_kappa(a, ["u" if x == "s" else "s" for x in a]) == -1.0
    assert cohen_kappa(["s"] * 4, ["s"] * 4) == 0.0  # both constant: undefined, reported as 0.0
    # textbook example: 20 items, observed agreement 0.7, expected 0.5 -> kappa 0.4
    a = ["s"] * 10 + ["u"] * 10
    b = ["s"] * 7 + ["u"] * 3 + ["s"] * 3 + ["u"] * 7
    assert round(cohen_kappa(a, b), 4) == 0.4


def test_agreement_and_length_check():
    assert agreement(["s", "u"], ["s", "s"]) == 0.5
    with pytest.raises(ValueError):
        agreement(["s"], [])


def test_committed_set_shape_and_balance():
    items = load_items(ROOT / "calibration" / "faithfulness")
    assert len(items) >= 50
    labels = [i.label for i in items]
    assert abs(labels.count("supported") - labels.count("unsupported")) <= 2
    assert len({i.id for i in items}) == len(items)
    assert all(i.provenance["license"] == "MIT" for i in items)
    assert all(i.context and i.response for i in items)


def test_load_items_rejects_duplicate_ids(tmp_path: Path):
    row = json.dumps(
        {
            "id": "x",
            "context": "c",
            "question": "",
            "response": "r",
            "label": "supported",
            "provenance": {"dataset": "t", "license": "MIT"},
        }
    )
    (tmp_path / "a.jsonl").write_text(row + "\n" + row + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_items(tmp_path)


def _items():
    return [
        CalibrationItem(
            id=f"i{n}",
            context="Paris is in France.",
            question="Where is Paris?",
            response="Paris is in France." if n % 2 == 0 else "Paris is in Spain.",
            label="supported" if n % 2 == 0 else "unsupported",
            provenance={"dataset": "t", "license": "MIT"},
        )
        for n in range(8)
    ]


def _judge(tmp_path: Path, name: str, outputs: list[str]) -> JudgeGrader:
    # mockllm's custom_outputs must be ModelOutput instances, not raw text
    # (see tests/test_judge.py: a bare str fails its isinstance check).
    scripted = [ModelOutput.from_content(model="mockllm", content=text) for text in outputs]
    return JudgeGrader(
        model=f"mockllm/{name}",
        rubric=RUBRICS["faithfulness"],
        cache=JudgeCache(tmp_path / name),
        model_handle=get_model("mockllm/model", custom_outputs=scripted),
    )


def test_calibrate_perfect_and_flipped_judges(tmp_path: Path):
    right = ["VERDICT: SUPPORTED" if n % 2 == 0 else "VERDICT: UNSUPPORTED" for n in range(8)]
    wrong = ["VERDICT: UNSUPPORTED" if n % 2 == 0 else "VERDICT: SUPPORTED" for n in range(8)]
    report = calibrate(_items(), [_judge(tmp_path, "a", right), _judge(tmp_path, "b", wrong)])
    a, b = report.judges
    assert (a.kappa, a.accuracy, a.unknown) == (1.0, 1.0, 0)
    assert b.kappa == -1.0
    assert report.swap_agreement == 0.0
    assert report.calibrated(a.judge) == (False, "swap agreement 0.00 < 0.90")
    assert report.calibrated(b.judge)[0] is False


def test_calibrate_unknowns_are_excluded_from_kappa(tmp_path: Path):
    outs = ["VERDICT: SUPPORTED" if n % 2 == 0 else "VERDICT: UNSUPPORTED" for n in range(8)]
    outs[3] = "no verdict here"
    report = calibrate(_items(), [_judge(tmp_path, "a", outs)])
    (j,) = report.judges
    assert j.unknown == 1 and j.items == 8 and j.kappa == 1.0
    assert report.swap_agreement is None
    assert report.calibrated(j.judge) == (
        True,
        "kappa 1.00 >= 0.70; single judge, swap agreement not measured",
    )


def test_write_report_promotes_latest(tmp_path: Path):
    outs = ["VERDICT: SUPPORTED" if n % 2 == 0 else "VERDICT: UNSUPPORTED" for n in range(8)]
    report = calibrate(_items(), [_judge(tmp_path, "a", outs)])
    path = write_report(report, tmp_path / "results")
    latest = json.loads((tmp_path / "results" / "calibration" / "latest.json").read_text())
    assert latest["judges"][0]["kappa"] == 1.0 and path.exists()


def test_cli_calibrate_runs_on_mock(tmp_path: Path, capsys):
    items_dir = tmp_path / "cal"
    items_dir.mkdir()
    with (items_dir / "t.jsonl").open("w", encoding="utf-8") as f:
        for i in _items():
            f.write(i.model_dump_json() + "\n")
    code = main(
        [
            "calibrate",
            "--items",
            str(items_dir),
            "--judge",
            "mockllm/model",
            "--results",
            str(tmp_path / "r"),
            "--cache",
            str(tmp_path / "c"),
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "kappa" in out and (tmp_path / "r" / "calibration" / "latest.json").exists()
