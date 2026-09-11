from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from eval_platform.budget import Budget
from eval_platform.suites import run_suite
from eval_platform.targets import ScriptedTarget
from eval_platform.telemetry import span
from eval_platform.types import Case, Expect

_exporter = InMemorySpanExporter()
_provider = TracerProvider()
_provider.add_span_processor(SimpleSpanProcessor(_exporter))
trace.set_tracer_provider(_provider)


def _case(name: str) -> Case:
    return Case(
        name=name,
        goal="g",
        target_requirements=["scripted"],
        script=[
            {"kind": "tool", "name": "lookup", "output": "v", "cost_usd": 0.001, "latency_ms": 2},
            {"kind": "model", "name": "final", "status": "completed", "answer": "done"},
        ],
        expect=Expect(status="completed"),
    )


def test_suite_and_case_spans_are_emitted_with_attributes():
    _exporter.clear()
    run_suite("offline_core", [_case("a"), _case("b")], ScriptedTarget(), budget=Budget(1, 60))
    spans = {s.name: s for s in _exporter.get_finished_spans()}
    suite_span = spans["eval.suite"]
    assert suite_span.attributes is not None
    assert suite_span.attributes["cases"] == 2
    assert suite_span.context is not None
    cases = [s for s in _exporter.get_finished_spans() if s.name == "eval.case"]
    assert len(cases) == 2
    case_span = cases[0]
    assert case_span.attributes is not None
    assert case_span.attributes["case"] in {"a", "b"}
    assert case_span.attributes["eval.passed"] is True
    assert case_span.attributes["eval.status"] == "completed"
    assert case_span.parent is not None
    assert case_span.parent.span_id == suite_span.context.span_id


def test_span_helper_sets_attributes_up_front():
    _exporter.clear()
    with span("eval.test", suite="s", n=3):
        pass
    [s] = _exporter.get_finished_spans()
    assert s.attributes is not None
    assert s.attributes["suite"] == "s" and s.attributes["n"] == 3
