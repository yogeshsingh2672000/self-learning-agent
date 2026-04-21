"""
Search providers for internet search functionality.
"""
from .base import SearchProvider, SearchResult
from .google import GoogleSearchProvider
from .duckduckgo import DuckDuckGoSearchProvider
from .bing import BingSearchProvider
from .serpapi import SerpAPISearchProvider

__all__ = [
    "SearchProvider",
    "SearchResult",
    "GoogleSearchProvider",
    "DuckDuckGoSearchProvider",
    "BingSearchProvider",
    "SerpAPISearchProvider",
]
