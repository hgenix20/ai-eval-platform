"""Targets: systems under test, and the protocol they share."""

from .agent_platform_http import AgentPlatformHttpTarget
from .agent_platform_local import AgentPlatformLocalTarget
from .base import AgentTarget, TargetUnavailable
from .scripted import ScriptedTarget

__all__ = [
    "AgentPlatformHttpTarget",
    "AgentPlatformLocalTarget",
    "AgentTarget",
    "ScriptedTarget",
    "TargetUnavailable",
]
