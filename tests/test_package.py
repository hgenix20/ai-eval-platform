import eval_platform


def test_version_is_semver():
    major, minor, patch = eval_platform.__version__.split(".")
    assert all(part.isdigit() for part in (major, minor, patch))
