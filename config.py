
import os
from typing import Dict

from dotenv import load_dotenv

from constants import (
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_TEMPERATURE,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TOP_P,
    DEFAULT_MAX_CONTEXT_LENGTH,
    PROVIDERS,
)
from llm import LLMConfig, OpenAIProvider, AnthropicProvider, GeminiProvider

load_dotenv()


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


def _get_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value else default


class Config:
    def __init__(self):
        # Load default LLM configuration from constants
        llm_config = LLMConfig(
            system_prompt=os.getenv("GENERATION_SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT),
            temperature=_get_float("GENERATION_TEMPERATURE", DEFAULT_TEMPERATURE),
            max_tokens=_get_int("GENERATION_MAX_TOKENS", DEFAULT_MAX_TOKENS),
            top_p=_get_float("GENERATION_TOP_P", DEFAULT_TOP_P),
            max_context_length=_get_int("GENERATION_MAX_CONTEXT_LENGTH", DEFAULT_MAX_CONTEXT_LENGTH),
        )
        
        # Initialize LLM providers
        self.llm_providers: Dict[str, object] = {}
        
        # Dynamically add providers based on available API keys
        provider_classes = {
            "openai": OpenAIProvider,
            "anthropic": AnthropicProvider,
            "gemini": GeminiProvider,
        }
        
        for provider_key, provider_info in PROVIDERS.items():
            api_key_env = provider_info["api_key_env"]
            if os.getenv(api_key_env):
                provider_class = provider_classes[provider_key]
                self.llm_providers[provider_key] = provider_class(llm_config)
    
    def get_provider(self, provider_name: str = "openai"):
        """Get a specific LLM provider by name"""
        if provider_name not in self.llm_providers:
            available = list(self.llm_providers.keys())
            raise ValueError(
                f"Provider '{provider_name}' not found. Available providers: {available}"
            )
        return self.llm_providers[provider_name]
    
    def list_providers(self):
        """List all available providers"""
        return list(self.llm_providers.keys())