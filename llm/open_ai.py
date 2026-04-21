import os
from typing import Optional

from constants import PROVIDERS
from .base import LLMProvider, LLMConfig


class OpenAIProvider(LLMProvider):
    """OpenAI API provider"""
    
    def __init__(self, config: LLMConfig, api_key: Optional[str] = None):
        super().__init__(config)
        provider_info = PROVIDERS["openai"]
        self.api_key = api_key or os.getenv(provider_info["api_key_env"])
        self.model = os.getenv(provider_info["model_env"], provider_info["default_model"])
    
    async def generate(self, prompt: str) -> str:
        """Generate text using OpenAI API"""
        if not self.validate_api_key():
            raise ValueError("OpenAI API key not configured")
        
        try:
            from openai import AsyncOpenAI
            
            client = AsyncOpenAI(api_key=self.api_key)
            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.config.system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                top_p=self.config.top_p,
            )
            return response.choices[0].message.content
        except ImportError:
            raise ImportError("openai package not installed. Install with: pip install openai")
    
    def validate_api_key(self) -> bool:
        """Check if OpenAI API key is configured"""
        return bool(self.api_key)
