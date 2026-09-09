"""The committed catalog must validate, be large enough, and every
inspect_evals runner ref must resolve to a real task in the installed
inspect_evals registry."""

from pathlib import Path

import inspect_evals._registry as registry

from eval_platform.catalog import load_catalog

ENTRIES = Path(__file__).resolve().parents[1] / "catalog" / "entries"


def test_catalog_has_at_least_sixty_entries():
    assert len(load_catalog(ENTRIES)) >= 60


def test_every_inspect_evals_ref_resolves():
    missing = []
    for e in load_catalog(ENTRIES):
        if e.runner.kind == "inspect_evals":
            assert e.runner.ref is not None
            task = e.runner.ref.removeprefix("inspect_evals/")
            if not callable(getattr(registry, task, None)):
                missing.append(e.runner.ref)
    assert missing == [], f"unresolved inspect_evals refs: {missing}"


def test_non_commercial_entries_are_flagged_not_runnable():
    entries = load_catalog(ENTRIES)
    nc = [e for e in entries if e.license.status == "non-commercial"]
    assert {e.id for e in nc} >= {"crmarena", "nolima", "crag"}
    assert all(not e.runnable for e in nc)


def test_every_category_is_represented():
    cats = {e.category for e in load_catalog(ENTRIES)}
    assert cats == {
        "capability",
        "coding",
        "tool-use",
        "agent",
        "long-context",
        "retrieval",
        "hallucination",
        "safety",
        "injection",
        "judge",
    }
