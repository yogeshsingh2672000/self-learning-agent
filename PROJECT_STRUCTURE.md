# Project Structure - LangChain Search Agent

## Directory Structure

```
self-learning-agent/
├── agent.py                 ⭐ Core SearchAgent class
├── app.py                   ⭐ CLI interface
├── constants.py             ⭐ Central configuration
├── requirements.txt         Dependencies
├── .env.example            Environment variables template
├── README.md               Project documentation
├── guide.py                Quick start guide
├── .git/                   Version control
├── .venv/                  Python virtual environment
└── .env                    (Create from .env.example)
```

## File Descriptions

### Core Agent Files

**agent.py**

- `SearchAgent` class - Core LangChain agent
- Tool-calling agent for autonomous reasoning
- OpenAI integration via `langchain_openai.ChatOpenAI`
- DuckDuckGo search via `langchain_community.tools.DuckDuckGoSearchRun`
- Interactive and single-query modes
- Conversation history support

**app.py**

- Command-line interface entry point
- `argparse` for CLI argument parsing
- Interactive conversation mode
- Single query mode (`-q` flag)
- Verbose logging (`-v` flag)
- LLM provider selection (`-l` flag)

### Configuration

**constants.py**

- Single source of truth for all configuration
- LLM provider metadata (names, defaults, API keys)
- Generation parameters (temperature, max_tokens)
- Used by `agent.py` for initialization

### Documentation

**README.md** - Comprehensive project documentation with usage examples

**guide.py** - Quick start guide and code examples

**requirements.txt** - Python dependencies (minimal and focused)

## Dependencies

```
LangChain Framework:
- langchain>=0.1.0
- langchain-openai>=0.0.0
- langchain-core>=0.1.0
- langchain-community>=0.0.0   (for DuckDuckGoSearchRun)

LLM Provider:
- openai>=1.3.0

Utilities:
- python-dotenv>=1.0.1
- pydantic>=2.0
```

## Architecture

The agent uses LangChain's **tool-calling agent** pattern:

1. **User Query** → `SearchAgent.answer(query)`
2. **LLM Decision** → OpenAI decides if search is needed
3. **Tool Execution** → If needed, calls `DuckDuckGoSearchRun()`
4. **Processing** → LLM synthesizes results with answer
5. **Response** → Returns final answer to user

## What Was Removed

### Deleted Files

- `search_providers/` - Custom search provider implementations
- `langchain_tools.py` - Custom tool wrappers
- `search.py` - SearchManager class
- `config.py` - Old LLM configuration system
- `llm/` - Old LLM provider wrappers

### Why Deleted

- **search_providers/** - LangChain has built-in DuckDuckGoSearchRun
- **langchain_tools.py** - Use LangChain tools directly
- **search.py** - No longer needed with LangChain integration
- **config.py** - Replaced by constants.py + agent.py
- **llm/** - LangChain handles LLM integration natively

## Code Statistics

| Metric        | Before | After | Change |
| ------------- | ------ | ----- | ------ |
| Files         | 15+    | 7     | -53%   |
| Lines of Code | 1500+  | 900   | -40%   |
| Dependencies  | 11     | 6     | -45%   |

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set up environment
cp .env.example .env
# Add your OPENAI_API_KEY to .env

# 3. Run the agent
python app.py

# Or run a single query
python app.py -q "Your question here"

# Verbose mode to see agent reasoning
python app.py -v
```

## Design Principles

✅ **Use LangChain's built-in tools** - Don't reinvent the wheel  
✅ **Single source of truth** - Configuration in `constants.py`  
✅ **Minimal custom code** - Focus on agent logic, not infrastructure  
✅ **Simple and clear** - Easy to understand and extend

## Future Enhancements

- Additional search tools (Tavily, SerpAPI via LangChain)
- More LLM providers (Claude, Gemini via LangChain)
- Conversation memory/persistence
- Web API endpoint
- Custom system prompts
- Multi-document RAG integration
