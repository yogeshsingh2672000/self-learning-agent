# Scalable Tool System Guide

This guide explains how to add new tools to the agent and extend its capabilities.

## Architecture Overview

The agent uses a **pluggable tool system** that makes it easy to add new features without modifying core agent code.

### Key Components

1. **`tools/base.py`** - Base tool interface (`BaseTool`, `ToolConfig`)
2. **`tools/registry.py`** - Tool registry that auto-discovers and loads tools
3. **`tools/*.py`** - Individual tool implementations (e.g., `search.py`)
4. **`agent.py`** - Agent that uses tools from registry (tool-agnostic)

### How It Works

```
User adds new tool file → Auto-discovered by ToolRegistry → Agent uses tool
```

## Adding a New Tool - Step by Step

### Step 1: Create a New Tool File

Create a file in the `tools/` directory (e.g., `tools/calculator.py`):

```python
"""
Calculator tool - Simple example tool.
"""
from langchain_core.tools import Tool
from .base import BaseTool, ToolConfig


class CalculatorTool(BaseTool):
    """Simple calculator tool"""

    def get_config(self) -> ToolConfig:
        """Define tool metadata"""
        return ToolConfig(
            name="calculator",
            description="Perform mathematical calculations. "
                       "Input: math expression (e.g., '2 + 2' or 'sqrt(16)')",
            enabled=True,
            category="math"
        )

    def execute(self) -> Tool:
        """Create and return the tool"""
        def calculate(expression: str) -> str:
            try:
                result = eval(expression)
                return f"Result: {result}"
            except Exception as e:
                return f"Error: {str(e)}"

        return Tool(
            name="calculator",
            func=calculate,
            description="Perform mathematical calculations. "
                       "Input: math expression (e.g., '2 + 2' or 'sqrt(16)')"
        )

    def validate_config(self) -> bool:
        """Validate tool configuration"""
        # No API keys needed for calculator
        return True
```

### Step 2: Tool Will Auto-Load

That's it! The tool is automatically discovered and loaded by `ToolRegistry`.

Run the agent and your tool will be available:

```bash
python app.py
```

Or check available tools:

```bash
python app.py --list-tools
```

You should see:

```
📌 calculator
   Description: Perform mathematical calculations...
   Category: math
```

## Tool Interface Reference

### BaseTool Class

All tools must inherit from `BaseTool` and implement two methods:

#### `get_config() -> ToolConfig`

Return tool metadata:

```python
def get_config(self) -> ToolConfig:
    return ToolConfig(
        name="unique_tool_name",           # Unique identifier
        description="What this tool does", # Shown to LLM
        enabled=True,                      # Enable/disable tool
        category="category_name",          # Organization
        requires_api_key="ENV_VAR_NAME"   # Optional: API key requirement
    )
```

#### `execute() -> Tool`

Create and return a LangChain `Tool` object:

```python
def execute(self) -> Tool:
    from langchain_core.tools import Tool

    def my_function(input_text: str) -> str:
        # Implementation
        return "result"

    return Tool(
        name="tool_name",
        func=my_function,
        description="Tool description shown to LLM"
    )
```

#### `validate_config() -> bool` (Optional)

Validate configuration before execution (e.g., check API keys):

```python
def validate_config(self) -> bool:
    """Check if tool is properly configured"""
    import os
    api_key = os.getenv("MY_API_KEY")
    return bool(api_key)
```

## Tool Examples

### Example 1: Weather Tool (with API key)

```python
"""tools/weather.py"""
import os
from langchain_core.tools import Tool
from .base import BaseTool, ToolConfig


class WeatherTool(BaseTool):
    """Get current weather information"""

    def get_config(self) -> ToolConfig:
        return ToolConfig(
            name="weather",
            description="Get current weather for a city. "
                       "Input: city name (e.g., 'New York')",
            enabled=True,
            category="information",
            requires_api_key="WEATHER_API_KEY"  # Requires API key
        )

    def execute(self) -> Tool:
        api_key = os.getenv("WEATHER_API_KEY")

        def get_weather(city: str) -> str:
            # Implementation using weather API
            return f"Weather in {city}: Sunny, 72°F"

        return Tool(
            name="weather",
            func=get_weather,
            description="Get current weather for a city"
        )

    def validate_config(self) -> bool:
        """Check if API key is set"""
        return bool(os.getenv("WEATHER_API_KEY"))
```

### Example 2: File Tool (file operations)

```python
"""tools/file_reader.py"""
from pathlib import Path
from langchain_core.tools import Tool
from .base import BaseTool, ToolConfig


class FileReaderTool(BaseTool):
    """Read text files"""

    def get_config(self) -> ToolConfig:
        return ToolConfig(
            name="read_file",
            description="Read content of a text file. "
                       "Input: file path (e.g., 'documents/notes.txt')",
            enabled=True,
            category="file_operations"
        )

    def execute(self) -> Tool:
        def read_file(file_path: str) -> str:
            try:
                path = Path(file_path)
                if not path.exists():
                    return f"File not found: {file_path}"
                content = path.read_text()
                return content[:1000]  # First 1000 chars
            except Exception as e:
                return f"Error reading file: {str(e)}"

        return Tool(
            name="read_file",
            func=read_file,
            description="Read content of a text file"
        )
```

## Using Tools in Your Code

### List Available Tools

```python
from tools import ToolRegistry

registry = ToolRegistry()
registry.print_tools_info()
```

### Get Specific Tool

```python
registry = ToolRegistry()
calculator = registry.get_tool("calculator")
langchain_tool = calculator.execute()
```

### Enable Only Specific Tools

```python
from agent import create_search_agent

# Create agent with only search tool
agent = create_search_agent(
    enabled_tools=["search_internet"]
)
```

### CLI Tool Selection

```bash
# List all tools
python app.py --list-tools

# Enable specific tools
python app.py -t "search_internet,calculator,weather"

# Interactive mode with specific tools
python app.py -t "search_internet" -i
```

## Best Practices

### 1. **Clear Tool Names and Descriptions**

```python
# Good
name="search_internet"
description="Search the internet for current information..."

# Bad
name="tool1"
description="Does stuff"
```

### 2. **Handle Errors Gracefully**

```python
def my_tool(input: str) -> str:
    try:
        result = perform_operation(input)
        return f"Success: {result}"
    except Exception as e:
        return f"Error: {str(e)}"  # Don't crash, return error message
```

### 3. **Validate Configuration**

```python
def validate_config(self) -> bool:
    api_key = os.getenv("MY_API_KEY")
    if not api_key:
        print("Warning: MY_API_KEY not set")
        return False
    return True
```

### 4. **Add to `tools/__init__.py`** (Optional but Recommended)

```python
from .calculator import CalculatorTool
__all__ = ["CalculatorTool"]
```

### 5. **Test Your Tool**

```python
# test_my_tool.py
from tools.my_tool import MyTool

tool_instance = MyTool()
langchain_tool = tool_instance.execute()
result = langchain_tool.func("test input")
print(result)
```

## Tool Categories (Convention)

Use these categories for organization:

- `information` - Search, lookup, retrieval
- `productivity` - Task management, reminders
- `math` - Calculations, statistics
- `file_operations` - Read/write files
- `web` - Web scraping, HTTP requests
- `integration` - External service integration
- `utility` - General utility

## Troubleshooting

### Tool Not Loading

1. Check file is in `tools/` directory
2. Verify class inherits from `BaseTool`
3. Check `get_config()` returns `ToolConfig`
4. Check `execute()` returns LangChain `Tool`
5. Run with `-v` flag to see errors:
   ```bash
   python app.py -v
   ```

### Tool Not Showing in List

1. Check `enabled=True` in `ToolConfig`
2. Check `validate_config()` returns `True`
3. Run with `--list-tools` to debug:
   ```bash
   python app.py --list-tools
   ```

### Tool Errors During Execution

1. Implement `validate_config()` to check requirements
2. Return error strings instead of raising exceptions
3. Test tool independently first:
   ```python
   from tools.my_tool import MyTool
   tool = MyTool()
   print(tool.validate_config())
   ```

## Summary

Adding a new tool is simple:

1. Create a file in `tools/` inheriting from `BaseTool`
2. Implement `get_config()` and `execute()`
3. Tool auto-loads when agent starts
4. Agent can now use the new tool

The scalable design lets you grow the agent with new capabilities without touching core agent code!
