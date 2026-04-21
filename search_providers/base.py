"""
Base class for search providers.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class SearchResult:
    """Represents a single search result"""
    title: str
    url: str
    description: str
    position: int = 0


class SearchProvider(ABC):
    """Abstract base class for internet search providers"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
    
    @abstractmethod
    async def search(self, query: str, num_results: int = 10) -> List[SearchResult]:
        """Search the internet for the given query"""
        pass
    
    @abstractmethod
    def validate_api_key(self) -> bool:
        """Validate that the API key is configured"""
        pass
