"""
Search module for finding information on the internet.
Supports multiple search providers: Google, DuckDuckGo, Bing, SerpAPI
"""
import os
from typing import List, Optional, Dict

from dotenv import load_dotenv

from constants import SEARCH_PROVIDERS
from search_providers import (
    SearchResult,
    GoogleSearchProvider,
    DuckDuckGoSearchProvider,
    BingSearchProvider,
    SerpAPISearchProvider,
)

load_dotenv()


class SearchManager:
    """Manager for handling multiple search providers"""
    
    def __init__(self):
        """Initialize available search providers based on API keys"""
        self.providers: Dict[str, object] = {}
        self._register_providers()
    
    def _register_providers(self):
        """Register available search providers based on configuration"""
        provider_classes = {
            "google_search": GoogleSearchProvider,
            "duckduckgo": DuckDuckGoSearchProvider,
            "bing_search": BingSearchProvider,
            "serpapi": SerpAPISearchProvider,
        }
        
        # DuckDuckGo doesn't need API key, always available
        self.providers["duckduckgo"] = DuckDuckGoSearchProvider()
        
        # Register other providers if API keys are available
        for provider_key, provider_info in SEARCH_PROVIDERS.items():
            if provider_key == "duckduckgo":
                continue  # Already registered
            
            api_key_env = provider_info.get("api_key_env")
            if api_key_env and os.getenv(api_key_env):
                provider_class = provider_classes[provider_key]
                
                if provider_key == "serpapi":
                    # SerpAPI can use different engines
                    self.providers[provider_key] = provider_class(
                        api_key=os.getenv(api_key_env),
                        engine="google"
                    )
                else:
                    self.providers[provider_key] = provider_class(
                        api_key=os.getenv(api_key_env)
                    )
    
    async def search(
        self,
        query: str,
        provider: str = "duckduckgo",
        num_results: int = 10
    ) -> List[SearchResult]:
        """
        Search the internet using the specified provider
        
        Args:
            query: Search query
            provider: Provider name (duckduckgo, google_search, bing_search, serpapi)
            num_results: Number of results to return
        
        Returns:
            List of SearchResult objects
        """
        if provider not in self.providers:
            available = list(self.providers.keys())
            raise ValueError(
                f"Provider '{provider}' not available. "
                f"Available providers: {available}"
            )
        
        search_provider = self.providers[provider]
        return await search_provider.search(query, num_results)
    
    def get_provider(self, provider_name: str):
        """Get a specific search provider"""
        if provider_name not in self.providers:
            available = list(self.providers.keys())
            raise ValueError(
                f"Provider '{provider_name}' not found. "
                f"Available: {available}"
            )
        return self.providers[provider_name]
    
    def list_providers(self) -> List[str]:
        """List all available search providers"""
        return list(self.providers.keys())
    
    def get_provider_info(self, provider_name: str) -> Dict:
        """Get metadata for a specific provider"""
        if provider_name not in SEARCH_PROVIDERS:
            raise ValueError(f"Unknown provider: {provider_name}")
        return SEARCH_PROVIDERS[provider_name]


# Global search manager instance
_search_manager = None


def get_search_manager() -> SearchManager:
    """Get the global search manager instance"""
    global _search_manager
    if _search_manager is None:
        _search_manager = SearchManager()
    return _search_manager


async def search(
    query: str,
    provider: str = "duckduckgo",
    num_results: int = 10
) -> List[SearchResult]:
    """
    Convenience function to search the internet
    
    Args:
        query: Search query
        provider: Provider name (default: duckduckgo)
        num_results: Number of results to return
    
    Returns:
        List of SearchResult objects
    
    Example:
        results = await search("Python programming")
        for result in results:
            print(f"{result.title}: {result.url}")
    """
    manager = get_search_manager()
    return await manager.search(query, provider, num_results)


def get_providers() -> List[str]:
    """Get list of available search providers"""
    manager = get_search_manager()
    return manager.list_providers()
