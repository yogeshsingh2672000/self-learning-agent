# Self-Learning Agent

A Python project that provides a unified interface for interacting with multiple LLM providers and internet search providers.

## Supported LLM Providers

- **OpenAI** - GPT-4, GPT-3.5-Turbo, and other OpenAI models
- **Anthropic Claude** - Claude 3 (Opus, Sonnet, Haiku)
- **Google Gemini** - Gemini Pro and other Google models

## Supported Search Providers

- **DuckDuckGo** - Free, no API key required
- **Google Search** - Via SerpAPI
- **Bing Search** - Bing Search API
- **SerpAPI** - Supports multiple search engines (Google, Bing, Baidu, Yahoo, etc.)

## Installation

1. Clone the repository:

```bash
git clone <repository-url>
cd self-learning-agent
```

2. Create a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

1. Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

2. Add your API keys to `.env`:

```
OPENAI_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here
GOOGLE_API_KEY=your_key_here
```

3. (Optional) Customize generation parameters in `.env`

## Usage

### Basic Usage

```python
import asyncio
from config import Config

async def main():
    config = Config()

    # List available providers
    print(config.list_providers())  # ['openai', 'anthropic', 'gemini']

    # Get a specific provider
    provider = config.get_provider('openai')

    # Generate text
    response = await provider.generate("What is AI?")
    print(response)

asyncio.run(main())
```

### Using Different Providers

```python
# Use OpenAI
openai_provider = config.get_provider('openai')
response = await openai_provider.generate("Hello!")

# Use Anthropic Claude
claude_provider = config.get_provider('anthropic')
response = await claude_provider.generate("Hello!")

# Use Google Gemini
gemini_provider = config.get_provider('gemini')
response = await gemini_provider.generate("Hello!")
```

### Search Usage

```python
import asyncio
from search import search, get_providers

async def main():
    # List available search providers
    print(get_providers())  # ['ddg', 'google_search', ...]

    # Search with DuckDuckGo (free, default)
    results = await search("machine learning", provider="ddg", num_results=5)

    for result in results:
        print(f"Title: {result.title}")
        print(f"URL: {result.url}")
        print(f"Description: {result.description}\n")

    # Search with Google (requires SerpAPI key)
    results = await search("AI algorithms", provider="google_search", num_results=10)

    # Search with Bing (requires Bing Search API key)
    results = await search("neural networks", provider="bing_search")

asyncio.run(main())
```

### Advanced Search Example

```python
import asyncio
from search import SearchManager

async def main():
    search_manager = SearchManager()

    # Get available providers
    print(search_manager.list_providers())

    # Search using a specific provider
    results = await search_manager.search(
        query="Python web frameworks",
        provider="ddg",
```

## Architecture

### Single Source of Truth

**`constants.py`** is the central source of truth for:

- Provider metadata (API key env vars, model env vars, default models)
- Default configuration parameters (temperature, max_tokens, etc.)

All other files import from `constants.py` to avoid duplication and ensure consistency.

### Base Classes

- **`LLMConfig`** - Configuration dataclass with common parameters (temperature, max_tokens, etc.)
- **`LLMProvider`** - Abstract base class for all LLM providers

### Provider Implementations

- **`OpenAIProvider`** - OpenAI API integration
- **`AnthropicProvider`** - Anthropic Claude API integration
- **`GeminiProvider`** - Google Gemini API integration

## Project Structure

```
self-learning-agent/
├── app.py              # Example application
├── config.py           # LLM configuration management
├── search.py           # Search functionality
├── constants.py        # Single source of truth for defaults & metadata
├── requirements.txt    # Python dependencies
├── .env.example        # Environment variables template
├── README.md           # This file
├── llm/
│   ├── __init__.py     # Package initialization
│   ├── base.py         # Base classes
│   ├── open_ai.py      # OpenAI provider
│   ├── anthropic.py    # Anthropic Claude provider
│   └── gemini.py       # Google Gemini provider
└── search_providers/
    ├── __init__.py     # Package initialization
    ├── base.py         # SearchProvider base class
    ├── google.py       # Google Search provider
    ├── duckduckgo.py   # DuckDuckGo (ddg) provider
    ├── bing.py         # Bing Search provider
    └── serpapi.py      # SerpAPI provider
```

## Environment Variables

### LLM Configuration

| Variable                        | Description                      | Example                  |
| ------------------------------- | -------------------------------- | ------------------------ |
| `OPENAI_API_KEY`                | OpenAI API key                   | `sk-...`                 |
| `OPENAI_MODEL`                  | OpenAI model to use              | `gpt-4`                  |
| `ANTHROPIC_API_KEY`             | Anthropic API key                | `sk-ant-...`             |
| `ANTHROPIC_MODEL`               | Anthropic model to use           | `claude-3-opus-20240229` |
| `GOOGLE_API_KEY`                | Google API key                   | `AIza...`                |
| `GOOGLE_MODEL`                  | Google model to use              | `gemini-pro`             |
| `GENERATION_TEMPERATURE`        | Temperature for generation (0-1) | `0.1`                    |
| `GENERATION_MAX_TOKENS`         | Max tokens to generate           | `2000`                   |
| `GENERATION_TOP_P`              | Top-p sampling parameter         | `0.9`                    |
| `GENERATION_MAX_CONTEXT_LENGTH` | Max context length               | `8000`                   |

### Search Configuration

| Variable              | Description                        | Example      |
| --------------------- | ---------------------------------- | ------------ |
| `SERPAPI_API_KEY`     | SerpAPI key for Google/Bing/etc    | `0987654...` |
| `BING_SEARCH_API_KEY` | Bing Search API key                | `0987654...` |
| (DuckDuckGo - ddg)   | No API key required for DuckDuckGo | N/A          |

## Running the Example

```bash
python app.py
```

## Development

### Adding a New LLM Provider

To maintain the single source of truth, follow these steps:

1. **Add provider metadata to `constants.py`**:

   ```python
   PROVIDERS = {
       "new_provider": {
           "name": "Provider Name",
           "api_key_env": "NEW_PROVIDER_API_KEY",
           "model_env": "NEW_PROVIDER_MODEL",
           "default_model": "model-name",
           "description": "Provider description",
       },
       ...
   }
   ```

2. **Create provider class** in `llm/new_provider.py` implementing `LLMProvider`

3. **Export in `llm/__init__.py`**:

   ```python
   from .new_provider import NewProviderClass
   __all__ = [..., "NewProviderClass"]
   ```

4. **Add to `config.py`** in the `provider_classes` dict:

   ```python
   provider_classes = {
       ...
       "new_provider": NewProviderClass,
   }
   ```

5. **Update `.env.example`** with new environment variables (referencing `constants.py`)

6. **Update `README.md`** with new provider information

### Adding a New Search Provider

1. **Add provider metadata to `constants.py`** in `SEARCH_PROVIDERS`:

   ```python
   SEARCH_PROVIDERS = {
       "new_search": {
           "name": "New Search Provider",
           "api_key_env": "NEW_SEARCH_API_KEY",
           "class_name": "NewSearchProvider",
           "description": "Description of the provider",
       },
       ...
   }
   ```

2. **Create provider class** in `search_providers/new_search.py` implementing `SearchProvider`:

   ```python
   from .base import SearchProvider, SearchResult

   class NewSearchProvider(SearchProvider):
       async def search(self, query: str, num_results: int = 10) -> List[SearchResult]:
           # Implementation here
           pass

       def validate_api_key(self) -> bool:
           return bool(self.api_key)
   ```

3. **Export in `search_providers/__init__.py`**:

   ```python
   from .new_search import NewSearchProvider
   __all__ = [..., "NewSearchProvider"]
   ```

4. **Register in `search.py`** in the `provider_classes` dict:

   ```python
   provider_classes = {
       ...
       "new_search": NewSearchProvider,
   }
   ```

5. **Update `.env.example`** and `README.md`

### Design Principles

- **Single Source of Truth**: All defaults, provider metadata, and configuration are defined in `constants.py`
- **DRY (Don't Repeat Yourself)**: Import from constants rather than hardcoding values
- **Easy to Extend**: Adding a new provider requires minimal changes across files
- **Async-First**: All search and LLM operations are async for better performance

## License

MIT
