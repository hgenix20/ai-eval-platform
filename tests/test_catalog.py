from datetime import date
from pathlib import Path

import pytest

from eval_platform.catalog import CatalogError, filter_entries, load_catalog

GOOD = """
id: gpqa-diamond
name: GPQA Diamond
url: https://github.com/idavidrein/gpqa
category: capability
maintainer: Rein et al.
size: "198"
license: {code: MIT, data: CC-BY-4.0, status: ambiguous}
scoring: exact-match
runner: {kind: inspect_evals, ref: inspect_evals/gpqa_diamond}
status: approaching-saturation
cost_class: low
requires: [hf-gated]
verified: 2026-09-07
sources: [https://github.com/idavidrein/gpqa]
notes: still in every 2026 system card
"""


def _write(d: Path, name: str, text: str) -> None:
    (d / name).write_text(text, encoding="utf-8")


def test_loads_valid_entry(tmp_path):
    _write(tmp_path, "gpqa.yaml", GOOD)
    [e] = load_catalog(tmp_path)
    assert e.id == "gpqa-diamond" and e.verified == date(2026, 9, 7) and e.runnable


def test_rejects_missing_sources_and_names_file(tmp_path):
    _write(
        tmp_path,
        "bad.yaml",
        GOOD.replace("sources: [https://github.com/idavidrein/gpqa]", "sources: []"),
    )
    with pytest.raises(CatalogError, match=r"bad\.yaml"):
        load_catalog(tmp_path)


def test_rejects_duplicate_url(tmp_path):
    _write(tmp_path, "a.yaml", GOOD)
    _write(tmp_path, "b.yaml", GOOD.replace("id: gpqa-diamond", "id: gpqa-two"))
    with pytest.raises(CatalogError, match="duplicate url"):
        load_catalog(tmp_path)


def test_rejects_duplicate_id(tmp_path):
    _write(tmp_path, "a.yaml", GOOD)
    _write(
        tmp_path,
        "b.yaml",
        GOOD.replace("url: https://github.com/idavidrein/gpqa", "url: https://example.org/other"),
    )
    with pytest.raises(CatalogError, match="duplicate id"):
        load_catalog(tmp_path)


def test_runner_ref_required_unless_none(tmp_path):
    _write(
        tmp_path,
        "x.yaml",
        GOOD.replace(
            "runner: {kind: inspect_evals, ref: inspect_evals/gpqa_diamond}",
            "runner: {kind: inspect_evals}",
        ),
    )
    with pytest.raises(CatalogError):
        load_catalog(tmp_path)


def test_runner_none_needs_no_ref(tmp_path):
    _write(
        tmp_path,
        "x.yaml",
        GOOD.replace(
            "runner: {kind: inspect_evals, ref: inspect_evals/gpqa_diamond}",
            "runner: {kind: none}",
        ),
    )
    [e] = load_catalog(tmp_path)
    assert e.runner.ref is None and not e.runnable


def test_rejects_unknown_top_level_key(tmp_path):
    _write(tmp_path, "bad.yaml", GOOD + "unknown_field: nope\n")
    with pytest.raises(CatalogError, match=r"bad\.yaml"):
        load_catalog(tmp_path)


def test_non_commercial_is_never_runnable(tmp_path):
    _write(tmp_path, "x.yaml", GOOD.replace("status: ambiguous", "status: non-commercial"))
    [e] = load_catalog(tmp_path)
    assert not e.runnable


def test_filter_by_category_and_status(tmp_path):
    _write(tmp_path, "a.yaml", GOOD)
    _write(
        tmp_path,
        "b.yaml",
        GOOD.replace("id: gpqa-diamond", "id: other")
        .replace("url: https://github.com/idavidrein/gpqa", "url: https://example.org/b")
        .replace("category: capability", "category: safety"),
    )
    entries = load_catalog(tmp_path)
    assert [e.id for e in filter_entries(entries, category="safety")] == ["other"]
    assert len(filter_entries(entries, status="approaching-saturation")) == 2
