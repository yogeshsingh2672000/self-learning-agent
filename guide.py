"""
LangChain agent quick start guide and examples.
"""

QUICK_START = """
╔═════════════════════════════════════════════════════════════════╗
║           LANGCHAIN SEARCH AGENT - QUICK START                  ║
╚═════════════════════════════════════════════════════════════════╝

1. INSTALLATION
   pip install -r requirements.txt

2. CONFIGURATION
   Copy .env.example to .env and add your API keys:
   - OPENAI_API_KEY=your_key_here

3. RUN INTERACTIVE MODE
   python app.py
   
   Then ask questions like:
   - "What are the latest developments in AI?"
   - "How does quantum computing work?"
   - "Best Python frameworks for web development?"

4. RUN SINGLE QUERY
   python app.py -q "Your question here"

5. ADVANCED USAGE
   # Use different LLM provider
   python app.py -l openai -s duckduckgo -i
   
   # Verbose mode (see agent reasoning)
   python app.py -v
   
   # Different search provider
   python app.py -s google_search

════════════════════════════════════════════════════════════════════

AVAILABLE OPTIONS:
  -q, --query       Single query to answer (non-interactive)
  -l, --llm         LLM provider: openai (default), anthropic, gemini
  -s, --search      Search provider: duckduckgo (default), google_search, bing_search, serpapi
  -v, --verbose     Show agent reasoning and tool usage
  -i, --interactive Interactive conversation mode

════════════════════════════════════════════════════════════════════

PYTHON API USAGE:

from agent import create_search_agent

# Create agent
agent = create_search_agent(
    llm_provider="openai",
    search_provider="duckduckgo",
    temperature=0.7,
    verbose=True
)

# Ask a question
response = agent.answer("What is machine learning?")
print(response)

# Interactive mode
agent.run_interactive()

════════════════════════════════════════════════════════════════════
"""

EXAMPLES = """
╔═════════════════════════════════════════════════════════════════╗
║                      EXAMPLE QUERIES                            ║
╚═════════════════════════════════════════════════════════════════╝

Scientific Questions:
- "What are the latest discoveries in quantum computing?"
- "How does photosynthesis work?"
- "Explain the theory of relativity in simple terms"

Technology:
- "What are the top programming languages in 2024?"
- "How does machine learning differ from deep learning?"
- "Best practices for API design"

Current Events:
- "What are the latest tech industry trends?"
- "Recent breakthroughs in renewable energy"
- "Major AI developments in 2024"

General Knowledge:
- "What are the benefits of exercise?"
- "How to learn a new language effectively?"
- "History of the internet"

════════════════════════════════════════════════════════════════════
"""

if __name__ == "__main__":
    print(QUICK_START)
    print(EXAMPLES)
