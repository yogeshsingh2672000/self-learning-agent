from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMConfig:
    """Base configuration for all LLM providers"""
    system_prompt: str = ""
    temperature: float = 0.1
    max_tokens: int = 2000
    top_p: float = 0.9
    max_context_length: int = 8000


class LLMProvider(ABC):
    """Abstract base class for LLM providers"""
    
    def __init__(self, config: LLMConfig):
        self.config = config
    
    @abstractmethod
    async def generate(self, prompt: str) -> str:
        """Generate text based on the prompt"""
        pass
    
    @abstractmethod
    def validate_api_key(self) -> bool:
        """Validate that the API key is configured"""
        pass
