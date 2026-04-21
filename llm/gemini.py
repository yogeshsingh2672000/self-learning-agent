import os
from typing import Optional

from constants import PROVIDERS
from .base import LLMProvider, LLMConfig


class GeminiProvider(LLMProvider):
    """Google Gemini API provider"""
    
    def __init__(self, config: LLMConfig, api_key: Optional[str] = None):
        super().__init__(config)
        provider_info = PROVIDERS["gemini"]
        self.api_key = api_key or os.getenv(provider_info["api_key_env"])
        self.model = os.getenv(provider_info["model_env"], provider_info["default_model"])
    
    async def generate(self, prompt: str) -> str:
        """Generate text using Google Gemini API"""
        if not self.validate_api_key():
            raise ValueError("Google API key not configured")
        
        try:
            import google.generativeai as genai
            
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(
                self.model,
                system_instruction=self.config.system_prompt
            )
            
            response = model.generate_content(
                prompt,
                generation_config={
                    "temperature": self.config.temperature,
                    "top_p": self.config.top_p,
                    "max_output_tokens": self.config.max_tokens,
                }
            )
            return response.text
        except ImportError:
            raise ImportError("google-generativeai package not installed. Install with: pip install google-generativeai")
    
    def validate_api_key(self) -> bool:
        """Check if Google API key is configured"""
        return bool(self.api_key)
