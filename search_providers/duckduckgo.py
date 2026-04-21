"""
DuckDuckGo search provider (no API key required).
"""
from typing import List

from .base import SearchProvider, SearchResult


class DuckDuckGoSearchProvider(SearchProvider):
    """DuckDuckGo search (free, no API key required)"""
    
    def __init__(self):
        super().__init__(api_key=None)
        self.provider_name = "DuckDuckGo"
    
    async def search(self, query: str, num_results: int = 10) -> List[SearchResult]:
        """Search using DuckDuckGo"""
        try:
            from duckduckgo_search import DDGS
            
            results = []
            with DDGS() as ddgs:
                ddgs_results = ddgs.text(query, max_results=num_results)
                for i, result in enumerate(ddgs_results, 1):
                    results.append(
                        SearchResult(
                            title=result.get("title", ""),
                            url=result.get("href", ""),
                            description=result.get("body", ""),
                            position=i,
                        )
                    )
            
            return results
        except ImportError:
            raise ImportError("duckduckgo-search package not installed. Install with: pip install duckduckgo-search")
        except Exception as e:
            raise RuntimeError(f"DuckDuckGo error: {str(e)}")
    
    def validate_api_key(self) -> bool:
        """DuckDuckGo doesn't require API key"""
        return True
