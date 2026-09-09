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


def test_two_writes_in_the_same_second_do_not_collide(tmp_path):
    # Same suite, target, and started_at: the two calls would compute the
    # same filename stem, so the second must not overwrite the first.
    first = write_summary(_res(target="scripted"), tmp_path)
    second = write_summary(_res(target="scripted"), tmp_path)
    assert first != second
    assert first.exists() and second.exists()
    latest = latest_summary(tmp_path, "offline_core")
    assert latest is not None
    assert read_summary(second) == latest
