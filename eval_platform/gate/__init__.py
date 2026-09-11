"""The regression gate: config, comparison, and report rendering."""

from .compare import GateReport, MetricVerdict, compare
from .config import GateConfig, JudgeRules, Threshold, load_gate_config
from .junit import to_junit
from .markdown import to_markdown

__all__ = [
    "GateConfig",
    "GateReport",
    "JudgeRules",
    "MetricVerdict",
    "Threshold",
    "compare",
    "load_gate_config",
    "to_junit",
    "to_markdown",
]
