# ADR-0003: the catalog's registry key is the primary URL

Status: accepted, 2026-09-08. Spec sections 4.1 and 10, decision 3.

## Context

The catalog is 77 YAML files, one benchmark each, seeded from the three
research inventories under `docs/research/`. Benchmark names collide:
`docs/research/2026-09-07-capability-benchmarks.md` records that "MCP-Bench"
names two distinct projects, and the catalog files Accenture's as
`mcp-bench-accenture` at `https://github.com/Accenture/mcp-bench`. A name is
what a paper chose; a repository or paper URL is what the thing is.

## Decision

`url` is the identity of a catalog entry and must be unique across the
directory. `id` is a slug and must also be unique, but it exists for the CLI
and for filenames, not for identity. `load_catalog` builds both maps as it
reads and raises `CatalogError` naming the offending file on either kind of
duplicate. The whole load fails; there is no partial catalog.

## Alternatives rejected

- **Key on `name`.** Two MCP-Bench entries then either collide or get renamed
  to something no source calls them.
- **Key on `id` alone.** Slugs are ours, so two entries pointing at one
  repository under different slugs would both load and both be counted.
- **Allow duplicates and warn.** A warning in CI output is one nobody reads.

## Consequences

- Adding an entry that repeats an existing URL fails the build: every test in
  `tests/test_catalog_entries.py` loads the committed directory, and the load
  raises. `tests/test_catalog.py::test_rejects_duplicate_url` pins the loader
  behavior itself.
- Renaming a benchmark is a one-field edit and changes no identity.
- A benchmark with no stable URL cannot be catalogued, which is the intended
  outcome: every entry also has to carry `verified` and at least one source.
