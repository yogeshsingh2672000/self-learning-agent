"""
SerpAPI search provider (supports multiple search engines).
"""
import os
from typing import List, Optional

from constants import PROVIDERS
from .base import SearchProvider, SearchResult


class SerpAPISearchProvider(SearchProvider):
    """SerpAPI provider (supports Google, Bing, Baidu, Yahoo, etc.)"""
    
    def __init__(self, api_key: Optional[str] = None, engine: str = "google"):
        super().__init__(api_key)
        provider_info = PROVIDERS.get("serpapi", {})
        self.api_key = api_key or os.getenv(provider_info.get("api_key_env", "SERPAPI_API_KEY"))
        self.engine = engine  # google, bing, baidu, yahoo, yandex, etc.
        self.provider_name = f"SerpAPI ({engine})"
    
    async def search(self, query: str, num_results: int = 10) -> List[SearchResult]:
        """Search using SerpAPI"""
        if not self.validate_api_key():
            raise ValueError("SerpAPI key not configured")
        
        try:
            import aiohttp
            
            endpoint = "https://serpapi.com/search"
            params = {
                "api_key": self.api_key,
                "q": query,
                "engine": self.engine,
                "num": num_results,
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    endpoint,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        raise RuntimeError(f"SerpAPI returned status {response.status}")
                    
                    data = await response.json()
                    
                    results = []
                    if "organic_results" in data:
                        for i, result in enumerate(data["organic_results"], 1):
                            results.append(
                                SearchResult(
                                    title=result.get("title", ""),
                                    url=result.get("link", ""),
                                    description=result.get("snippet", ""),
                                    position=i,
                                )
                            )
                    
                    return results
        except ImportError:
            raise ImportError("aiohttp package not installed. Install with: pip install aiohttp")
        except Exception as e:
            raise RuntimeError(f"SerpAPI error: {str(e)}")
    
    def validate_api_key(self) -> bool:
        """Check if API key is configured"""
        return bool(self.api_key)
