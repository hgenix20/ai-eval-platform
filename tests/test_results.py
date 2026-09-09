from eval_platform.results import latest_summary, read_summary, write_summary
from eval_platform.types import SuiteResult


def _res(suite="offline_core", target="scripted"):
    return SuiteResult(
        suite=suite,
        target=target,
        started_at="2026-09-08T10:00:00+00:00",
        finished_at="2026-09-08T10:00:01+00:00",
        cases=(),
        metrics={"pass_rate": 1.0},
        meta={},
    )


def test_write_then_read_and_latest(tmp_path):
    p = write_summary(_res(), tmp_path)
    assert p.exists() and read_summary(p)["metrics"]["pass_rate"] == 1.0
    latest = latest_summary(tmp_path, "offline_core")
    assert latest is not None and latest["target"] == "scripted"
    assert latest_summary(tmp_path, "nope") is None
