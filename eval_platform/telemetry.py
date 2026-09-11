"""OpenTelemetry spans around evaluation work.

API only: this package never installs a tracer provider (the agent platform's
ADR-0005 rule, mirrored here). Without an SDK the spans are no-ops; with one,
every case, suite, and public run becomes a span carrying tokens, cost,
latency, and outcome attributes.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.trace import Span

TRACER_NAME = "eval_platform"


def get_tracer() -> trace.Tracer:
    """Return this package's tracer, as registered under `TRACER_NAME`.

    Contract: never raises. With no SDK-backed provider installed, the
    returned tracer produces no-op spans, so calling this in a test or a
    small deployment with no tracing configured costs nothing.
    """
    return trace.get_tracer(TRACER_NAME)


@contextmanager
def span(name: str, **attributes: str | int | float | bool) -> Iterator[Span]:
    """Open a span named `name` with `attributes` set before the body runs.

    Contract: attribute values must be str, int, float, or bool (the
    OpenTelemetry primitive types); anything else is coerced with str() so
    a stray value never breaks tracing. The span ends when the `with`
    block exits, including on an exception raised inside it; this context
    manager itself never raises beyond what the body raises.
    """
    with get_tracer().start_as_current_span(name) as s:
        for key, value in attributes.items():
            s.set_attribute(
                key, value if isinstance(value, str | int | float | bool) else str(value)
            )
        yield s
