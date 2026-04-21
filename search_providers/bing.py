"""
Bing Search provider.
"""
import os
from typing import List, Optional

from constants import PROVIDERS
from .base import SearchProvider, SearchResult


class BingSearchProvider(SearchProvider):
    """Bing Search provider"""
    
    def __init__(self, api_key: Optional[str] = None):
        super().__init__(api_key)
        provider_info = PROVIDERS.get("bing_search", {})
        self.api_key = api_key or os.getenv(provider_info.get("api_key_env", "BING_SEARCH_API_KEY"))
        self.endpoint = "https://api.bing.microsoft.com/v7.0/search"
        self.provider_name = "Bing Search"
    
    async def search(self, query: str, num_results: int = 10) -> List[SearchResult]:
        """Search using Bing Search API"""
        if not self.validate_api_key():
            raise ValueError("Bing Search API key not configured")
        
        try:
            import aiohttp
            
            headers = {"Ocp-Apim-Subscription-Key": self.api_key}
            params = {"q": query, "count": num_results}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.endpoint,
                    headers=headers,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        raise RuntimeError(f"Bing API returned status {response.status}")
                    
                    data = await response.json()
                    
                    results = []
                    if "webPages" in data:
                        for i, result in enumerate(data["webPages"]["value"], 1):
                            results.append(
                                SearchResult(
                                    title=result.get("name", ""),
                                    url=result.get("url", ""),
                                    description=result.get("snippet", ""),
                                    position=i,
                                )
                            )
                    
                    return results
        except ImportError:
            raise ImportError("aiohttp package not installed. Install with: pip install aiohttp")
        except Exception as e:
            raise RuntimeError(f"Bing Search error: {str(e)}")
    
    def validate_api_key(self) -> bool:
        """Check if API key is configured"""
        return bool(self.api_key)
