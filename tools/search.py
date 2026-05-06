"""
Internet search tool using DuckDuckGo.
Example tool implementation following the BaseTool interface.
"""
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.tools import Tool

from .base import BaseTool, ToolConfig


class SearchTool(BaseTool):
    """
    Internet search tool using DuckDuckGo.
    
    Features:
    - No API key required (uses DuckDuckGo)
    - Fast and reliable search results
    - Can be used as a template for other tools
    
    Usage:
        tool = SearchTool()
        langchain_tool = tool.execute()
        # Pass to agent
    """
    
    def get_config(self) -> ToolConfig:
        """Get search tool configuration"""
        return ToolConfig(
            name="search_internet",
            description="Search the internet using DuckDuckGo. "
                       "Use this to find current information, facts, news, or any web content. "
                       "Input: search query (string)",
            enabled=True,
            category="information"
        )
    
    def execute(self) -> Tool:
        """
        Create and return the LangChain search tool.
        
        Returns:
            Tool: LangChain Tool object ready for agent use
        """
        # Use LangChain's built-in DuckDuckGo search
        search_tool = DuckDuckGoSearchRun()
        
        # Wrap in Tool for consistency
        return Tool(
            name="search_internet",
            func=lambda query: search_tool.run(query),
            description="Search the internet using DuckDuckGo. "
                       "Use this to find current information, facts, news, or any web content. "
                       "Input: search query (string)"
        )
    
    def validate_config(self) -> bool:
        """
        Validate tool configuration.
        DuckDuckGo doesn't require API keys, so always valid.
        
        Returns:
            bool: Always True for DuckDuckGo
        """
        return True
