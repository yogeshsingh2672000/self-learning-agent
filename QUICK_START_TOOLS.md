# Quick Start - Adding Tools

## TL;DR - Add a Tool in 30 Seconds

### 1. Create `tools/my_tool.py`

```python
from langchain_core.tools import Tool
from tools.base import BaseTool, ToolConfig


class MyTool(BaseTool):
    def get_config(self) -> ToolConfig:
        return ToolConfig(
            name="my_tool",
            description="What my tool does",
            enabled=True,
            category="utility"
        )

    def execute(self) -> Tool:
        def my_func(input_text: str) -> str:
            return f"Result: {input_text.upper()}"

        return Tool(
            name="my_tool",
            func=my_func,
            description="What my tool does"
        )
```

### 2. List Tools

```bash
python app.py --list-tools
```

Your tool appears! 🎉

### 3. Use It

```bash
python app.py -q "Use my_tool to process something"
```

Agent uses your tool automatically!

---

## Tool Template

Copy this for every new tool:

```python
from langchain_core.tools import Tool
from tools.base import BaseTool, ToolConfig


class YourToolName(BaseTool):
    """One line description"""

    def get_config(self) -> ToolConfig:
        return ToolConfig(
            name="tool_id",
            description="Tool description shown to LLM",
            enabled=True,
            category="category_name"
        )

    def execute(self) -> Tool:
        def tool_function(input_text: str) -> str:
            try:
                # Your implementation here
                result = do_something(input_text)
                return f"Success: {result}"
            except Exception as e:
                return f"Error: {str(e)}"

        return Tool(
            name="tool_id",
            func=tool_function,
            description="Tool description"
        )

    # Optional: Validate configuration
    def validate_config(self) -> bool:
        return True
```

---

## Common Examples

### Calculator

```python
class CalculatorTool(BaseTool):
    def get_config(self) -> ToolConfig:
        return ToolConfig(
            name="calculator",
            description="Math: 2+2, sqrt(16), sin(0)",
            enabled=True,
            category="math"
        )

    def execute(self) -> Tool:
        def calc(expr: str) -> str:
            try:
                result = eval(expr)
                return f"{result}"
            except:
                return "Invalid expression"

        return Tool(
            name="calculator",
            func=calc,
            description="Math calculator"
        )
```

### With API Key

```python
import os

class APITool(BaseTool):
    def get_config(self) -> ToolConfig:
        return ToolConfig(
            name="api_tool",
            description="Query external API",
            enabled=True,
            category="integration",
            requires_api_key="MY_API_KEY"
        )

    def execute(self) -> Tool:
        api_key = os.getenv("MY_API_KEY")

        def call_api(query: str) -> str:
            import requests
            headers = {"Authorization": f"Bearer {api_key}"}
            # ... API call
            return "result"

        return Tool(
            name="api_tool",
            func=call_api,
            description="Query external API"
        )

    def validate_config(self) -> bool:
        return bool(os.getenv("MY_API_KEY"))
```

### Web Scraper

```python
class WebScraperTool(BaseTool):
    def get_config(self) -> ToolConfig:
        return ToolConfig(
            name="web_scraper",
            description="Get webpage content from URL",
            enabled=True,
            category="web"
        )

    def execute(self) -> Tool:
        def scrape(url: str) -> str:
            try:
                import requests
                resp = requests.get(url, timeout=10)
                return resp.text[:2000]
            except Exception as e:
                return f"Error: {str(e)}"

        return Tool(
            name="web_scraper",
            func=scrape,
            description="Get webpage content"
        )
```

---

## ToolConfig Options

```python
ToolConfig(
    name="unique_identifier",        # Required - used internally
    description="Shown to LLM",      # Required - LLM reads this
    enabled=True,                    # Optional - enable/disable
    category="category_name",        # Optional - organize tools
    requires_api_key="ENV_VAR"       # Optional - document requirement
)
```

### Categories

Common categories:

- `information` - Search, lookup
- `productivity` - Tasks, notes
- `math` - Calculations
- `file_operations` - File I/O
- `web` - Web requests, scraping
- `integration` - External APIs
- `utility` - General utilities

---

## Testing Your Tool

```python
# test_my_tool.py
from tools.my_tool import MyTool

tool = MyTool()

# Check config
config = tool.get_config()
print(f"Tool: {config.name}")

# Validate
assert tool.validate_config()

# Execute
langchain_tool = tool.execute()
result = langchain_tool.func("test input")
print(result)

assert "Error" not in result
print("✅ Tool works!")
```

Run with: `python test_my_tool.py`

---

## Using Tools

### Show Available Tools

```bash
python app.py --list-tools
```

### Use All Tools

```bash
python app.py -i
# or
python app.py -q "Your question"
```

### Use Specific Tools

```bash
# Single tool
python app.py -t "search_internet" -q "Query"

# Multiple tools
python app.py -t "search_internet,calculator" -i

# With verbose output
python app.py -t "calculator" -v -q "2+2"
```

### Python Code

```python
from agent import create_search_agent

# All tools
agent = create_search_agent()

# Specific tools
agent = create_search_agent(enabled_tools=["calculator"])

response = agent.answer("What is 5*5?")
print(response)
```

---

## Error Handling

### Right Way ✅

```python
def tool_func(input_text: str) -> str:
    try:
        result = do_something(input_text)
        return f"Success: {result}"
    except Exception as e:
        return f"Error: {str(e)}"  # Return error message
```

### Wrong Way ❌

```python
def tool_func(input_text: str) -> str:
    result = do_something(input_text)  # Will crash agent if error
    return result
```

---

## Tool File Locations

```
tools/
├── search.py              ← Current tool
├── my_tool.py            ← Your new tool
├── calculator.py         ← Another new tool
└── complex_tool.py       ← More tools
```

All `.py` files in `tools/` are auto-discovered!

---

## Full Tool Anatomy

```python
# 1. Imports at top
from langchain_core.tools import Tool
from tools.base import BaseTool, ToolConfig


# 2. Class inherits from BaseTool
class MyTool(BaseTool):
    """Docstring describes what tool does"""

    # 3. get_config() - Tool metadata
    def get_config(self) -> ToolConfig:
        return ToolConfig(
            name="unique_id",
            description="What tool does",
            enabled=True,
            category="category"
        )

    # 4. execute() - Return LangChain Tool
    def execute(self) -> Tool:
        # Inner function does actual work
        def inner_function(input_text: str) -> str:
            try:
                # Implementation
                return "result"
            except Exception as e:
                return f"Error: {str(e)}"

        # Return LangChain Tool wrapper
        return Tool(
            name="unique_id",
            func=inner_function,
            description="What tool does"
        )

    # 5. validate_config() - Optional
    def validate_config(self) -> bool:
        # Check API keys, dependencies, etc
        import os
        return bool(os.getenv("REQUIRED_KEY"))
```

---

## Checklist - Before Using Tool

- [ ] File in `tools/` directory
- [ ] Class inherits from `BaseTool`
- [ ] `get_config()` returns `ToolConfig`
- [ ] `execute()` returns `Tool`
- [ ] Tool name in config matches Tool name
- [ ] Description is clear (LLM reads it)
- [ ] Error handling (return strings, not exceptions)
- [ ] Test independently works

---

## Need Help?

1. Check existing tools:
   - `tools/search.py` - Simple, working tool
   - `tools/examples.py` - Multiple examples

2. Read guides:
   - `SCALABLE_ARCHITECTURE.md` - Architecture overview
   - `ARCHITECTURE.md` - Detailed guide
   - `TOOLS_GUIDE.md` - Comprehensive reference

3. Test:
   ```bash
   python app.py --list-tools
   python -c "from tools.my_tool import MyTool; print(MyTool().validate_config())"
   ```

---

## That's It!

Add tools, scale features, no core changes needed! 🚀
