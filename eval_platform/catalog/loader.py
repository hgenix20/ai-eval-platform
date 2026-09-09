"""Load the benchmark catalog from a directory of YAML files.

One file per benchmark; the catalog is a flat directory of `*.yaml` files, and
the URL (not the filename) is the unique key because filenames are free text
chosen by whoever adds an entry.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from .schema import CatalogEntry


class CatalogError(Exception):
    """Raised when a catalog file fails validation or violates a catalog-wide
    invariant (duplicate id or url). The message always names the offending
    file so a broken catalog can be fixed without a debugger."""


def load_catalog(directory: Path) -> list[CatalogEntry]:
    """Load and validate every `*.yaml` file directly under `directory`.

    Contract: each file must parse as YAML and validate against
    `CatalogEntry`; every entry's `id` and `url` must be unique across the
    whole directory. Returns entries sorted by `id`.

    Failure modes: raises `CatalogError` naming the file for a YAML parse
    error, a schema validation error, a duplicate `id`, or a duplicate `url`
    (message contains "duplicate url"). The whole load fails on the first
    problem found (files are processed in sorted filename order) rather than
    returning a partial catalog.
    """
    entries: list[CatalogEntry] = []
    seen_ids: dict[str, Path] = {}
    seen_urls: dict[str, Path] = {}
    for path in sorted(directory.glob("*.yaml")):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            entry = CatalogEntry.model_validate(raw)
        except (yaml.YAMLError, ValidationError) as e:
            raise CatalogError(f"{path.name}: {e}") from e
        if entry.id in seen_ids:
            raise CatalogError(
                f"{path.name}: duplicate id {entry.id} (also {seen_ids[entry.id].name})"
            )
        url = str(entry.url)
        if url in seen_urls:
            raise CatalogError(f"{path.name}: duplicate url {url} (also {seen_urls[url].name})")
        seen_ids[entry.id] = path
        seen_urls[url] = path
        entries.append(entry)
    return sorted(entries, key=lambda e: e.id)


def filter_entries(
    entries: list[CatalogEntry],
    *,
    category: str | None = None,
    status: str | None = None,
    runnable: bool | None = None,
) -> list[CatalogEntry]:
    """Return the subset of `entries` matching every given filter.

    Contract: filters are ANDed together; an omitted (`None`) filter passes
    everything through. Pure function: does not mutate or re-sort `entries`
    beyond preserving their existing relative order.
    """
    out = entries
    if category is not None:
        out = [e for e in out if e.category == category]
    if status is not None:
        out = [e for e in out if e.status == status]
    if runnable is not None:
        out = [e for e in out if e.runnable == runnable]
    return out
