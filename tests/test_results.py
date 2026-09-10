from eval_platform.results import latest_summary, read_summary, write_summary
from eval_platform.types import SuiteResult


def _res(suite="offline_core", target="scripted", pass_rate=1.0):
    return SuiteResult(
        suite=suite,
        target=target,
        started_at="2026-09-08T10:00:00+00:00",
        finished_at="2026-09-08T10:00:01+00:00",
        cases=(),
        metrics={"pass_rate": pass_rate},
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


def test_promote_latest_false_writes_per_run_file_but_not_latest(tmp_path):
    """A caller recording an errored run's per-run file must not let it
    become the published latest.json: with promote_latest=False, the
    timestamped file exists but latest.json is left exactly as it was."""
    write_summary(_res(pass_rate=1.0), tmp_path)
    before = read_summary(tmp_path / "offline_core" / "latest.json")

    errored = write_summary(_res(pass_rate=0.0), tmp_path, promote_latest=False)
    assert errored.exists()
    assert read_summary(errored)["metrics"]["pass_rate"] == 0.0
    assert read_summary(tmp_path / "offline_core" / "latest.json") == before


def test_promote_latest_false_with_no_existing_latest_leaves_it_absent(tmp_path):
    path = write_summary(_res(suite="public_ifeval"), tmp_path, promote_latest=False)
    assert path.exists()
    assert not (tmp_path / "public_ifeval" / "latest.json").exists()


def test_target_with_a_slash_writes_inside_the_suite_directory(tmp_path):
    # Inspect model ids carry a provider prefix, so `result.target` for a
    # public run contains a slash. It must not be read as a directory
    # separator: the file belongs in the suite directory, under one name.
    p = write_summary(_res(suite="public_ifeval", target="anthropic/claude-x"), tmp_path)
    assert p.parent == tmp_path / "public_ifeval"
    assert "/" not in p.name and "\\" not in p.name
    assert "anthropic_claude-x" in p.name
    assert read_summary(p)["target"] == "anthropic/claude-x"
    assert p.read_text(encoding="utf-8").endswith("\n")
