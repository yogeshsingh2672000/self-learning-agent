# Scalable Tooling System Documentation

This document explains the tool-based architecture and how to extend the agent with new capabilities.

## Overview

The agent uses a **pluggable tool system** that allows you to:

1. ✅ Add new tools without modifying agent code
2. ✅ Tools are automatically discovered and loaded
3. ✅ Each tool is independent and testable
4. ✅ Tools are composable (can use other tools)
5. ✅ Scale from 1 to 100+ tools easily

## Architecture

### Tool System Components

```
ToolRegistry (auto-discovery)
    ↓
    Scans tools/ directory
    ↓
    Finds all BaseTool subclasses
    ↓
Loads tools dynamically
    ↓
Agent uses tools via LangChain
```

### Key Principles

1. **Agent is Tool-Agnostic** - Agent doesn't know about specific tools
2. **Auto-Discovery** - Tools are found by scanning `tools/` directory
3. **Configuration as Interface** - Tools define themselves via `ToolConfig`
4. **Tool Registry** - Central place for managing all tools

## Quick Start - Adding Your First Tool

### 1. Create `tools/my_first_tool.py`

```python
from langchain_core.tools import Tool
from tools.base import BaseTool, ToolConfig


class MyFirstTool(BaseTool):
    """My first tool implementation"""

    def get_config(self) -> ToolConfig:
        return ToolConfig(
            name="my_first_tool",
            description="Does something awesome",
            enabled=True,
            category="utility"
        )

    def execute(self) -> Tool:
        def my_function(input_text: str) -> str:
            return f"Tool executed with: {input_text}"

        return Tool(
            name="my_first_tool",
            func=my_function,
            description="Does something awesome"
        )
```

### 2. That's It!

Your tool is automatically discovered. Verify with:

```bash
python app.py --list-tools
```

You should see `my_first_tool` in the output.

## Tool Interface - Required Methods

### `get_config() -> ToolConfig`

Define tool metadata that the agent will see:

```python
def get_config(self) -> ToolConfig:
    return ToolConfig(
        name="unique_identifier",        # Used internally
        description="What the tool does", # Shown to LLM
        enabled=True,                    # Enable/disable
        category="category_name",        # Organize tools
        requires_api_key="ENV_VAR_NAME"  # Optional
    )
```

### `execute() -> Tool`

Create and return the actual tool:

```python
def execute(self) -> Tool:
    from langchain_core.tools import Tool

    def tool_function(input_text: str) -> str:
        # Your implementation
        return result

    return Tool(
        name="tool_name",
        func=tool_function,
        description="Tool description"
    )
```

### `validate_config() -> bool` (Optional)

Override to check if tool is properly configured:

```python
def validate_config(self) -> bool:
    import os
    # Check for required API keys, environment variables, etc.
    return bool(os.getenv("REQUIRED_API_KEY"))
```

## Full Example - Weather Tool

```python
"""tools/weather.py"""
import os
from langchain_core.tools import Tool
from tools.base import BaseTool, ToolConfig


class WeatherTool(BaseTool):
    """Get weather information for a city"""

    def get_config(self) -> ToolConfig:
        return ToolConfig(
            name="get_weather",
            description="Get current weather information for a city. "
                       "Input: city name (e.g., 'New York', 'London')",
            enabled=True,
            category="information",
            requires_api_key="WEATHER_API_KEY"
        )

    def execute(self) -> Tool:
        api_key = os.getenv("WEATHER_API_KEY")

        def get_weather(city: str) -> str:
            try:
                import requests
                url = f"https://api.weather.example.com?city={city}&key={api_key}"
                response = requests.get(url)
                data = response.json()
                return f"Weather in {city}: {data['condition']}, {data['temp']}°"
            except Exception as e:
                return f"Error: Could not fetch weather - {str(e)}"

        return Tool(
            name="get_weather",
            func=get_weather,
            description="Get current weather for a city"
        )

    def validate_config(self) -> bool:
        api_key = os.getenv("WEATHER_API_KEY")
        if not api_key:
            print("Weather tool requires WEATHER_API_KEY environment variable")
            return False
        return True
```

## Running with Specific Tools

### List All Tools

```bash
python app.py --list-tools
```

### Use Only Specific Tools

```bash
# Use only search tool
python app.py -t "search_internet"

# Use multiple tools
python app.py -t "search_internet,calculator,weather"

# Interactive mode with specific tools
python app.py -t "search_internet,calculator" -i
```

### Python API

```python
from agent import create_search_agent

# All tools
agent = create_search_agent()

# Specific tools only
agent = create_search_agent(enabled_tools=["search_internet", "calculator"])

# Use agent
response = agent.answer("What is 2+2?")
```

## Tool Categories (Convention)

Organize your tools by category:

- `information` - Search, lookup, retrieval (search_internet, weather, etc.)
- `productivity` - Task management, reminders, notes
- `math` - Calculations, statistics, analysis
- `file_operations` - Read/write/process files
- `web` - Web scraping, HTTP requests
- `integration` - Third-party service integration
- `utility` - General utility tools

## Error Handling Best Practices

### Do:

```python
# Return error messages, don't raise exceptions
try:
    result = do_something()
    return f"Success: {result}"
except Exception as e:
    return f"Error: {str(e)}"
```

### Don't:

```python
# Don't let exceptions propagate
try:
    result = do_something()
except Exception:
    raise  # Bad - will crash the agent
```

## Testing Tools

Test your tool independently before using with agent:

```python
"""test_my_tool.py"""
from tools.my_tool import MyTool

def test_tool():
    # Create instance
    tool = MyTool()

    # Check config
    config = tool.get_config()
    print(f"Tool name: {config.name}")
    print(f"Description: {config.description}")

    # Validate
    assert tool.validate_config(), "Tool config is invalid"

    # Execute
    langchain_tool = tool.execute()

    # Test function
    result = langchain_tool.func("test input")
    print(f"Result: {result}")

    assert "Error" not in result, "Tool returned error"
    print("✅ Tool works!")

if __name__ == "__main__":
    test_tool()
```

## Examples - Copy and Modify

Use these as starting templates:

### Simple Tool (No External Dependencies)

```python
from tools.base import BaseTool, ToolConfig
from langchain_core.tools import Tool


class SimpleTool(BaseTool):
    def get_config(self) -> ToolConfig:
        return ToolConfig(
            name="simple",
            description="Simple tool",
            enabled=True,
            category="utility"
        )

    def execute(self) -> Tool:
        def simple_func(input_text: str) -> str:
            return f"Input was: {input_text}"

        return Tool(
            name="simple",
            func=simple_func,
            description="Simple tool"
        )
```

### Tool with API Key

```python
import os
from tools.base import BaseTool, ToolConfig
from langchain_core.tools import Tool


class APITool(BaseTool):
    def get_config(self) -> ToolConfig:
        return ToolConfig(
            name="api_tool",
            description="Tool that uses an API",
            enabled=True,
            category="integration",
            requires_api_key="MY_API_KEY"
        )

    def execute(self) -> Tool:
        api_key = os.getenv("MY_API_KEY")

        def api_func(query: str) -> str:
            # Use api_key here
            import requests
            headers = {"Authorization": f"Bearer {api_key}"}
            # ... API call
            return "Result from API"

        return Tool(
            name="api_tool",
            func=api_func,
            description="Tool that uses an API"
        )

    def validate_config(self) -> bool:
        return bool(os.getenv("MY_API_KEY"))
```

### Tool with Error Handling

```python
from tools.base import BaseTool, ToolConfig
from langchain_core.tools import Tool


class SafeTool(BaseTool):
    def get_config(self) -> ToolConfig:
        return ToolConfig(
            name="safe_tool",
            description="Tool with good error handling",
            enabled=True,
            category="utility"
        )

    def execute(self) -> Tool:
        def safe_func(input_text: str) -> str:
            try:
                if not input_text:
                    return "Error: Input cannot be empty"

                if len(input_text) > 1000:
                    return "Error: Input too long (max 1000 chars)"

                result = process_input(input_text)
                return f"Result: {result}"

            except ValueError as e:
                return f"Error: Invalid input - {str(e)}"
            except Exception as e:
                return f"Error: Unexpected error - {type(e).__name__}: {str(e)}"

        return Tool(
            name="safe_tool",
            func=safe_func,
            description="Tool with good error handling"
        )


def process_input(text):
    # Your implementation
    return text.upper()
```

## Built-in Examples

See `tools/examples.py` for working implementations:

- **CalculatorTool** - Simple math
- **TimeTool** - Date/time info
- **TextAnalyzerTool** - Text analysis
- **EnvironmentCheckerTool** - Check environment

Uncomment and import in `tools/__init__.py` to use.

## Debugging Tools

### Check if tool loads

```bash
python app.py --list-tools
```

### Test tool directly

```python
from tools.my_tool import MyTool

tool = MyTool()
print(tool.validate_config())
langchain_tool = tool.execute()
print(langchain_tool.func("test"))
```

### Use verbose mode

```bash
python app.py -v -q "Your query"
```

Shows agent reasoning and tool selection.

## Common Issues

### Tool doesn't appear in list

1. Check file is in `tools/` directory ✓
2. Check class inherits from `BaseTool` ✓
3. Check `get_config()` returns `ToolConfig` ✓
4. Check `execute()` returns `Tool` ✓
5. Check `enabled=True` in config ✓
6. Check `validate_config()` returns `True` ✓

### Tool errors during execution

Return error string instead of raising exception:

```python
# Good
return f"Error: {str(e)}"

# Bad
raise Exception("error message")
```

### Tool not being used

1. Tool config description should be clear
2. Tool should be in `--list-tools` output
3. Query should match tool capability
4. Run with `-v` flag to see agent's decisions

## Summary

Adding a tool is simple:

1. Create file `tools/my_tool.py`
2. Implement `BaseTool` with `get_config()` and `execute()`
3. Tool auto-loads when agent starts
4. Agent can now use it!

**No changes needed to agent or any other files.**

The scalable design keeps the codebase clean as you add more tools and features!
