import os
from typing import Optional

from constants import PROVIDERS
from .base import LLMProvider, LLMConfig


class AnthropicProvider(LLMProvider):
    """Anthropic Claude API provider"""
    
    def __init__(self, config: LLMConfig, api_key: Optional[str] = None):
        super().__init__(config)
        provider_info = PROVIDERS["anthropic"]
        self.api_key = api_key or os.getenv(provider_info["api_key_env"])
        self.model = os.getenv(provider_info["model_env"], provider_info["default_model"])
    
    async def generate(self, prompt: str) -> str:
        """Generate text using Anthropic Claude API"""
        if not self.validate_api_key():
            raise ValueError("Anthropic API key not configured")
        
        try:
            from anthropic import Anthropic
            
            client = Anthropic(api_key=self.api_key)
            response = client.messages.create(
                model=self.model,
                max_tokens=self.config.max_tokens,
                system=self.config.system_prompt,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            return response.content[0].text
        except ImportError:
            raise ImportError("anthropic package not installed. Install with: pip install anthropic")
    
    def validate_api_key(self) -> bool:
        """Check if Anthropic API key is configured"""
        return bool(self.api_key)
