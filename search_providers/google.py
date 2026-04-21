"""
Google Search provider using SerpAPI.
"""
import os
from typing import List, Optional

from constants import PROVIDERS
from .base import SearchProvider, SearchResult


class GoogleSearchProvider(SearchProvider):
    """Google Search using SerpAPI"""
    
    def __init__(self, api_key: Optional[str] = None):
        super().__init__(api_key)
        provider_info = PROVIDERS.get("google_search", {})
        self.api_key = api_key or os.getenv(provider_info.get("api_key_env", "SERPAPI_API_KEY"))
        self.provider_name = "Google (SerpAPI)"
    
    async def search(self, query: str, num_results: int = 10) -> List[SearchResult]:
        """Search Google using SerpAPI"""
        if not self.validate_api_key():
            raise ValueError("SerpAPI key not configured")
        
        try:
            import serpapi
            
            params = {
                "q": query,
                "num": num_results,
            }
            
            client = serpapi.Client(api_key=self.api_key)
            results = client.search(params)
            
            search_results = []
            if "organic_results" in results:
                for i, result in enumerate(results["organic_results"], 1):
                    search_results.append(
                        SearchResult(
                            title=result.get("title", ""),
                            url=result.get("link", ""),
                            description=result.get("snippet", ""),
                            position=i,
                        )
                    )
            
            return search_results
        except ImportError:
            raise ImportError("google-search-results package not installed. Install with: pip install google-search-results")
        except Exception as e:
            raise RuntimeError(f"SerpAPI error: {str(e)}")
    
    def validate_api_key(self) -> bool:
        """Check if API key is configured"""
        return bool(self.api_key)
