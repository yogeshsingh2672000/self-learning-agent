"""
Base tool interface for scalable tool system.
All tools must implement this interface.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class ToolConfig:
    """Configuration for a tool"""
    name: str
    description: str
    enabled: bool = True
    category: str = "utility"
    requires_api_key: Optional[str] = None


class BaseTool(ABC):
    """
    Base class for all tools.
    
    To create a new tool:
    1. Inherit from BaseTool
    2. Implement get_config() - return tool metadata
    3. Implement execute() - return LangChain Tool object
    
    Example:
    ```python
    class MyTool(BaseTool):
        def get_config(self) -> ToolConfig:
            return ToolConfig(
                name="my_tool",
                description="Does something awesome",
                category="productivity"
            )
        
        def execute(self) -> Tool:
            from langchain_core.tools import Tool
            
            def my_func(query: str) -> str:
                # Implementation
                return "result"
            
            return Tool(
                name="my_tool",
                func=my_func,
                description="Does something awesome"
            )
    ```
    """
    
    @abstractmethod
    def get_config(self) -> ToolConfig:
        """
        Get tool configuration and metadata.
        
        Returns:
            ToolConfig with tool metadata
        """
        pass
    
    @abstractmethod
    def execute(self):
        """
        Execute the tool and return a LangChain Tool object.
        
        Returns:
            langchain_core.tools.Tool: LangChain-compatible tool
        """
        pass
    
    def validate_config(self) -> bool:
        """
        Validate tool configuration (e.g., check API keys).
        Override in subclass if needed.
        
        Returns:
            bool: True if valid, False otherwise
        """
        return True
