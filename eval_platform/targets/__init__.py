"""Targets: systems under test, and the protocol they share."""

from .base import AgentTarget, TargetUnavailable
from .scripted import ScriptedTarget

__all__ = ["AgentTarget", "ScriptedTarget", "TargetUnavailable"]
