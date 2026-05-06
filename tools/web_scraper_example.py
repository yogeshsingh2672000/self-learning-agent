"""
Example: Adding a Web Scraper Tool

This file demonstrates how to create a more complex tool with error handling,
configuration validation, and external dependencies.

You can use this as a template for your own tools.
"""

from langchain_core.tools import Tool
from typing import Optional
import os

from tools.base import BaseTool, ToolConfig


class WebScraperTool(BaseTool):
    """
    Web scraper tool - Example of a tool with external dependencies.
    
    This is NOT auto-loaded (no __init__ export) - it's just an example.
    To use this tool:
    1. Uncomment the import in tools/__init__.py
    2. Add `from .examples.web_scraper import WebScraperTool` to tools/__init__.py
    3. The tool will auto-load next time you run the agent
    """
    
    def get_config(self) -> ToolConfig:
        """Define tool metadata"""
        return ToolConfig(
            name="web_scraper",
            description="Scrape content from a webpage URL. "
                       "Returns the main text content of the page. "
                       "Input: Full URL (e.g., 'https://example.com')",
            enabled=True,
            category="web",
            requires_api_key=None  # No API key needed
        )
    
    def execute(self) -> Tool:
        """Create the web scraper tool"""
        
        def scrape_webpage(url: str) -> str:
            """
            Scrape a webpage and return its content.
            
            Args:
                url: Full URL to scrape (e.g., 'https://example.com')
            
            Returns:
                Page content or error message
            """
            try:
                # Example using requests library
                import requests
                from bs4 import BeautifulSoup
                
                # Fetch the page
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
                }
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                
                # Parse with BeautifulSoup
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Remove script and style elements
                for script in soup(["script", "style"]):
                    script.decompose()
                
                # Get text
                text = soup.get_text()
                
                # Clean up text
                lines = (line.strip() for line in text.splitlines())
                chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                text = ' '.join(chunk for chunk in chunks if chunk)
                
                # Return first 2000 characters
                return text[:2000]
            
            except requests.exceptions.Timeout:
                return "Error: Request timed out (took more than 10 seconds)"
            except requests.exceptions.ConnectionError:
                return f"Error: Could not connect to {url}"
            except requests.exceptions.HTTPError as e:
                return f"Error: HTTP {e.response.status_code}"
            except Exception as e:
                return f"Error: {type(e).__name__}: {str(e)}"
        
        return Tool(
            name="web_scraper",
            func=scrape_webpage,
            description="Scrape content from a webpage URL. "
                       "Returns the main text content of the page. "
                       "Input: Full URL (e.g., 'https://example.com')"
        )
    
    def validate_config(self) -> bool:
        """
        Validate that required packages are installed.
        
        Returns:
            True if tool can run, False otherwise
        """
        try:
            import requests
            import bs4
            return True
        except ImportError:
            print("Warning: Web scraper requires 'requests' and 'beautifulsoup4'")
            print("Install with: pip install requests beautifulsoup4")
            return False


# ============================================================================
# UNCOMMENT BELOW TO USE THIS TOOL
# ============================================================================
#
# 1. Add this to tools/__init__.py:
#    from .web_scraper import WebScraperTool
#    __all__ = [..., "WebScraperTool"]
#
# 2. Create the tools/examples/ directory and move this file there
#
# 3. Run: python app.py --list-tools
#    You should see "web_scraper" in the list
#
# 4. Use in agent: The agent will automatically use this tool when needed
#
# ============================================================================
