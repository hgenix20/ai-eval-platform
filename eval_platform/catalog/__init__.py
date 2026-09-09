"""Benchmark catalog: pydantic schema plus a loader for the YAML registry."""

from .loader import CatalogError, filter_entries, load_catalog
from .schema import CatalogEntry

__all__ = ["CatalogEntry", "CatalogError", "filter_entries", "load_catalog"]
