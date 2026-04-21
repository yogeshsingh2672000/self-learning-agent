"""
Central configuration constants for the self-learning-agent project.
This is the single source of truth for all default values and provider metadata.
"""

# Generation/LLM Configuration Defaults
DEFAULT_TEMPERATURE = 0.1
DEFAULT_MAX_TOKENS = 2000
DEFAULT_TOP_P = 0.9
DEFAULT_MAX_CONTEXT_LENGTH = 8000
DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant."

# LLM Provider Configuration
# Each provider has: api_key_env_var, model_env_var, default_model
PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "api_key_env": "OPENAI_API_KEY",
        "model_env": "OPENAI_MODEL",
        "default_model": "gpt-4",
        "description": "GPT-4, GPT-3.5-Turbo, and other OpenAI models",
    },
    "anthropic": {
        "name": "Anthropic Claude",
        "api_key_env": "ANTHROPIC_API_KEY",
        "model_env": "ANTHROPIC_MODEL",
        "default_model": "claude-3-opus-20240229",
        "description": "Claude 3 (Opus, Sonnet, Haiku)",
    },
    "gemini": {
        "name": "Google Gemini",
        "api_key_env": "GOOGLE_API_KEY",
        "model_env": "GOOGLE_MODEL",
        "default_model": "gemini-pro",
        "description": "Gemini Pro and other Google models",
    },
}

# Search Provider Configuration
SEARCH_PROVIDERS = {
    "google_search": {
        "name": "Google Search",
        "api_key_env": "SERPAPI_API_KEY",
        "class_name": "GoogleSearchProvider",
        "description": "Google Search via SerpAPI",
    },
    "duckduckgo": {
        "name": "DuckDuckGo",
        "api_key_env": None,
        "class_name": "DuckDuckGoSearchProvider",
        "description": "DuckDuckGo (free, no API key required)",
    },
    "bing_search": {
        "name": "Bing Search",
        "api_key_env": "BING_SEARCH_API_KEY",
        "class_name": "BingSearchProvider",
        "description": "Bing Search API",
    },
    "serpapi": {
        "name": "SerpAPI",
        "api_key_env": "SERPAPI_API_KEY",
        "class_name": "SerpAPISearchProvider",
        "description": "SerpAPI (supports multiple engines)",
    },
}

# Environment Variable Names (for .env file)
ENV_VARS = {
    "openai_api_key": "OPENAI_API_KEY",
    "openai_model": "OPENAI_MODEL",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "anthropic_model": "ANTHROPIC_MODEL",
    "google_api_key": "GOOGLE_API_KEY",
    "google_model": "GOOGLE_MODEL",
    "generation_system_prompt": "GENERATION_SYSTEM_PROMPT",
    "generation_temperature": "GENERATION_TEMPERATURE",
    "generation_max_tokens": "GENERATION_MAX_TOKENS",
    "generation_top_p": "GENERATION_TOP_P",
    "generation_max_context_length": "GENERATION_MAX_CONTEXT_LENGTH",
}


def get_provider_info(provider_name: str) -> dict:
    """Get configuration info for a specific provider"""
    if provider_name not in PROVIDERS:
        raise ValueError(
            f"Unknown provider: {provider_name}. "
            f"Available: {list(PROVIDERS.keys())}"
        )
    return PROVIDERS[provider_name]


def get_all_provider_names() -> list:
    """Get list of all provider names"""
    return list(PROVIDERS.keys())
