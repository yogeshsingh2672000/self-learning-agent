"""
Tool registry and manager for dynamic tool loading.
Enables scalable addition of new tools without modifying agent code.
"""
import importlib
import inspect
from typing import List, Dict
from pathlib import Path

from .base import BaseTool, ToolConfig


class ToolRegistry:
    """
    Registry for managing all available tools.
    
    Dynamically discovers and loads tool implementations.
    Makes tools pluggable and configurable.
    
    Usage:
        registry = ToolRegistry()
        tools = registry.get_langchain_tools()  # Get all tools for agent
        
        # Check available tools
        tools_info = registry.get_available_tools()
    """
    
    def __init__(self, enabled_tools: List[str] = None):
        """
        Initialize the tool registry.
        
        Args:
            enabled_tools: List of tool names to enable.
                          If None, enables all tools with enabled=True in config.
        """
        self.enabled_tools = enabled_tools or []
        self.tools: Dict[str, BaseTool] = {}
        self._load_tools()
    
    def _load_tools(self):
        """
        Dynamically load all tool implementations from the tools directory.
        Discovers and instantiates all BaseTool subclasses.
        """
        # Get the tools directory
        tools_dir = Path(__file__).parent
        
        # Import all modules in tools directory
        for file in tools_dir.glob("*.py"):
            if file.name in ["__init__.py", "base.py"]:
                continue
            
            module_name = file.stem
            try:
                # Import the module
                module = importlib.import_module(f".{module_name}", package="tools")
                
                # Find all BaseTool subclasses in the module
                for name, obj in inspect.getmembers(module):
                    if (
                        inspect.isclass(obj)
                        and issubclass(obj, BaseTool)
                        and obj is not BaseTool
                    ):
                        # Instantiate and register the tool
                        tool_instance = obj()
                        config = tool_instance.get_config()
                        
                        # Check if tool should be enabled
                        should_enable = (
                            not self.enabled_tools  # If no filter, use config
                            or config.name in self.enabled_tools
                        )
                        
                        if config.enabled and should_enable:
                            self.tools[config.name] = tool_instance
                            print(f"✅ Loaded tool: {config.name}")
            
            except Exception as e:
                print(f"⚠️  Failed to load tool from {module_name}: {e}")
    
    def get_langchain_tools(self) -> List:
        """
        Get all tools converted to LangChain Tool format.
        
        Returns:
            List of langchain_core.tools.Tool objects ready for agent use
        """
        langchain_tools = []
        for tool_name, tool in self.tools.items():
            try:
                if tool.validate_config():
                    langchain_tools.append(tool.execute())
            except Exception as e:
                print(f"⚠️  Failed to execute tool {tool_name}: {e}")
        
        return langchain_tools
    
    def get_available_tools(self) -> Dict[str, ToolConfig]:
        """
        Get information about all available tools.
        
        Returns:
            Dict mapping tool names to their configurations
        """
        available = {}
        for tool_name, tool in self.tools.items():
            available[tool_name] = tool.get_config()
        return available
    
    def get_tool(self, name: str) -> BaseTool:
        """
        Get a specific tool by name.
        
        Args:
            name: Tool name
        
        Returns:
            BaseTool instance or None if not found
        """
        return self.tools.get(name)
    
    def list_tools(self) -> List[str]:
        """
        List all available tool names.
        
        Returns:
            List of tool names
        """
        return list(self.tools.keys())
    
    def print_tools_info(self):
        """Print formatted information about all available tools."""
        print("\n" + "=" * 70)
        print("AVAILABLE TOOLS")
        print("=" * 70)
        
        available = self.get_available_tools()
        if not available:
            print("No tools available.")
            return
        
        for tool_name, config in available.items():
            print(f"\n📌 {config.name}")
            print(f"   Description: {config.description}")
            print(f"   Category: {config.category}")
            if config.requires_api_key:
                print(f"   Requires: {config.requires_api_key}")
        
        print("\n" + "=" * 70 + "\n")
