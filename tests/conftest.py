"""Shared pytest fixtures.

Installs one OpenTelemetry SDK TracerProvider for the whole test session so
that no individual test module has to (and none can shadow another's):
`opentelemetry.trace.set_tracer_provider` only takes effect the first time
it is called in a process. If two modules each called it at import time,
the second call would be rejected by the SDK (it logs a warning and keeps
the first provider), so spans meant to go to the second module's exporter
would never reach it.
"""

from __future__ import annotations

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

_exporter = InMemorySpanExporter()
# A single-item list, not a plain bool, so the fixture below can flip it
# without a `global` statement (flagged by this repo's lint rule PLW0603).
_provider_installed = [False]


@pytest.fixture(scope="session", autouse=True)
def _telemetry_provider() -> None:
    """Install the session's TracerProvider exactly once.

    Contract: idempotent, guarded by the module-level `_provider_installed`
    flag so a second call in the same process (e.g. pytest-xdist reusing
    this module, or a future fixture depending on this one more than once)
    never tries to install a second provider.
    """
    if not _provider_installed[0]:
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(_exporter))
        trace.set_tracer_provider(provider)
        _provider_installed[0] = True


@pytest.fixture
def spans(_telemetry_provider: None) -> InMemorySpanExporter:
    """The session's in-memory span exporter, cleared before each test.

    Contract: depends on `_telemetry_provider` so the provider exists
    before a test reads from the exporter; clears any spans left over from
    an earlier test before returning, so each test sees only the spans its
    own body emits.
    """
    _exporter.clear()
    return _exporter
