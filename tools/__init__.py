"""
Tools package - Scalable tool system for the agent.

New tools are auto-discovered. Just add a file implementing BaseTool.
"""

from .base import BaseTool, ToolConfig
from .registry import ToolRegistry
from .search import SearchTool

__all__ = [
    "BaseTool",
    "ToolConfig",
    "ToolRegistry",
    "SearchTool",
]
