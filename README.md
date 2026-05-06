# Self-Learning Agent - Scalable Tool-Based Architecture

A **scalable AI agent** built with LangChain that uses a pluggable tool system. Start with internet search, then easily add new capabilities like calculators, web scrapers, file operations, APIs, and more—all without modifying core agent code.

## Key Architecture

✨ **Pluggable Tools** - Add tools without touching agent code  
🔧 **Auto-Discovery** - Tools are automatically loaded and registered  
📦 **Modular Design** - Each tool is independent and composable  
🚀 **Scalable** - From 1 tool to 100+ tools, architecture stays clean  
🧠 **Intelligent Selection** - LLM decides which tools to use  
💬 **Interactive & Programmatic** - Use via CLI or Python API

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

2. Add your OpenAI API key to `.env`:

```
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4
```

3. (Optional) Customize generation parameters in `.env`:

```
GENERATION_TEMPERATURE=0.7
GENERATION_MAX_TOKENS=2000
```

## Usage

### Interactive Mode (Default)

Run the agent in interactive conversation mode:

```bash
python app.py
```

Then ask questions naturally:

```
You: What are the latest developments in AI?
Agent: [Agent searches internet and answers...]

You: How does machine learning work?
Agent: [Agent provides comprehensive answer...]
```

### Single Query Mode

Get a quick answer without interactive mode:

```bash
python app.py -q "What is quantum computing?"
```

### Advanced Usage

#### Use Different LLM Models

```bash
# Use GPT-3.5-Turbo with verbose logging
python app.py -v

# Non-interactive mode
python app.py -q "Your question here"

# Interactive mode explicitly
python app.py -i
```

#### Python API

```python
from agent import create_search_agent

# Create agent
agent = create_search_agent(
    llm_provider="openai",
    temperature=0.7,
    verbose=True
)

# Ask a question
response = agent.answer("What is machine learning?")
print(response)

# Interactive conversation
agent.run_interactive()
```

#### Persistent Conversation

```python
from agent import create_search_agent
from langchain_core.messages import HumanMessage, AIMessage

agent = create_search_agent()

# Build conversation history
chat_history = []

# First question
response1 = agent.answer("What is Python?", chat_history)
chat_history.append(HumanMessage(content="What is Python?"))
chat_history.append(AIMessage(content=response1))

# Follow-up question (agent remembers context)
response2 = agent.answer("What can I build with it?", chat_history)
```

### Command Line Options

```
-q, --query       Single query to answer (non-interactive)
-l, --llm         LLM provider: openai (default)
-v, --verbose     Show agent reasoning and tool usage
-i, --interactive Force interactive mode (default if no query)
```

### Example Queries

```
Scientific Questions:
- "What are the latest breakthroughs in quantum computing?"
- "How does photosynthesis work?"
- "Explain CRISPR gene editing in simple terms"

Technology:
- "What are the top programming languages in 2024?"
- "Differences between machine learning and deep learning"
- "Best practices for microservices architecture"

Current Events:
- "Latest developments in AI"
- "Recent space exploration news"
- "Major tech industry acquisitions"

General Knowledge:
- "Benefits of regular exercise"
- "How to learn a new language"
- "History of the internet"
```

## Architecture

### Agent Design

The agent uses **LangChain's tool-calling agent** to implement a reasoning loop:

1. **Input** - User query
2. **Planning** - LLM decides whether to search
3. **Tool Use** - Executes DuckDuckGo search if needed
4. **Processing** - Synthesizes results
5. **Output** - Comprehensive answer

### Components

- **`agent.py`** - Core SearchAgent class using LangChain
- **`app.py`** - CLI interface (argparse)
- **`constants.py`** - Central configuration (single source of truth)

## Project Structure

```
self-learning-agent/
├── app.py                  # Main entry point (CLI)
├── agent.py                # SearchAgent class (LangChain integration)
├── constants.py            # Central configuration
├── guide.py                # Quick start guide
├── requirements.txt        # Python dependencies
├── .env.example            # Environment variables template
├── README.md               # This file
└── .git/                   # Version control
```

## Environment Variables

### LLM Configuration

| Variable                 | Description                      | Example  |
| ------------------------ | -------------------------------- | -------- |
| `OPENAI_API_KEY`         | OpenAI API key                   | `sk-...` |
| `OPENAI_MODEL`           | OpenAI model to use              | `gpt-4`  |
| `GENERATION_TEMPERATURE` | Temperature for generation (0-1) | `0.7`    |
| `GENERATION_MAX_TOKENS`  | Max tokens to generate           | `2000`   |

## Running the Agent

```bash
python app.py
```

## Design Principles

- **Simplicity First**: Uses LangChain's built-in tools and integrations
- **Single Source of Truth**: Configuration centralized in `constants.py`
- **No Custom Search Providers**: Leverages LangChain's DuckDuckGo integration
- **OpenAI Focused**: Optimized for OpenAI models (can be extended to others)

## Future Enhancements

Possible extensions to the agent:

- Add more LLM providers (Anthropic Claude, Google Gemini via LangChain)
- Add more search tools (Tavily, SerpAPI via LangChain)
- Persistent memory/conversation storage
- Web API endpoint
- Multi-turn conversation persistence
- Custom system prompts and configurations

## License

MIT
