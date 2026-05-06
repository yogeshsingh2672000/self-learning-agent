# Scalable Self-Learning Agent - Architecture Overview

## What We've Built

A **tool-based AI agent** with a **scalable, pluggable architecture** that lets you:

1. ✅ Start with internet search
2. ✅ Add new tools/features without touching agent code
3. ✅ Scale from 1 tool to 100+ tools cleanly
4. ✅ Let LLM intelligently choose which tools to use

## Key Innovation: Tool-Agnostic Agent

Traditional agent approach:

```
agent.py imports search_tool → imports calculator_tool → imports weather_tool → ...
              ↓
         Hard to add new tools
         Agent code gets complex
         Tight coupling
```

Our approach:

```
agent.py imports ToolRegistry
              ↓
ToolRegistry auto-discovers tools/
              ↓
Each tool = independent file
              ↓
Add new tool = Add 1 file (no other changes)
```

## Architecture Diagram

```
┌────────────────────────────────────────┐
│         SearchAgent (agent.py)         │
│   - Tool-agnostic (doesn't know       │
│     about specific tools)              │
│   - Uses LangChain tool-calling        │
│   - Gets tools from registry           │
└─────────────────┬──────────────────────┘
                  │
                  ▼
┌────────────────────────────────────────┐
│    ToolRegistry (tools/registry.py)    │
│   - Scans tools/ directory             │
│   - Auto-discovers BaseTool            │
│     subclasses                         │
│   - Creates LangChain tools            │
└─────┬────────────┬─────────┬──────────┘
      │            │         │
      ▼            ▼         ▼
  ┌───────┐  ┌──────────┐  ┌────────┐
  │Search │  │Calculator│  │Weather │  ...
  │Tool   │  │Tool      │  │Tool    │
  │       │  │          │  │        │
  │search │  │calculate │  │weather │
  │.py    │  │tool.py   │  │tool.py │
  └───────┘  └──────────┘  └────────┘
      ↑            ↑            ↑
      └────────────┴────────────┘
       All implement BaseTool
```

## File Structure

```
self-learning-agent/
├── agent.py                      Core agent (tool-agnostic)
├── app.py                        CLI interface
├── constants.py                  Configuration
│
├── tools/                        PLUGGABLE TOOLS DIRECTORY
│   ├── __init__.py              Exports tools
│   ├── base.py                  BaseTool interface (all tools inherit)
│   ├── registry.py              ToolRegistry (auto-discovery)
│   ├── search.py                🔍 SearchTool (internet search)
│   ├── examples.py              Example tools (calculator, time, etc.)
│   └── web_scraper_example.py   Complex example (web scraping)
│
├── ARCHITECTURE.md               This document - tool development
├── TOOLS_GUIDE.md               Tool development guide
└── [other files]
```

## Starting Point: Search Tool

The `SearchTool` is already implemented and working:

```python
# In tools/search.py
class SearchTool(BaseTool):
    """Internet search using DuckDuckGo"""

    def get_config(self) -> ToolConfig:
        return ToolConfig(
            name="search_internet",
            description="Search the internet...",
            enabled=True,
            category="information"
        )

    def execute(self) -> Tool:
        # Returns LangChain Tool
```

## Adding Your First New Tool - 3 Easy Steps

### Step 1: Create `tools/calculator.py`

```python
from langchain_core.tools import Tool
from tools.base import BaseTool, ToolConfig


class CalculatorTool(BaseTool):
    def get_config(self) -> ToolConfig:
        return ToolConfig(
            name="calculator",
            description="Perform math: 2+2, sqrt(16), etc",
            enabled=True,
            category="math"
        )

    def execute(self) -> Tool:
        def calc(expr: str) -> str:
            try:
                result = eval(expr)
                return f"Result: {result}"
            except:
                return "Invalid expression"

        return Tool(
            name="calculator",
            func=calc,
            description="Math calculator"
        )
```

### Step 2: Done!

Tool auto-loads. No other files to modify.

### Step 3: Verify

```bash
python app.py --list-tools
```

You should see:

```
📌 calculator
   Description: Perform math: 2+2, sqrt(16), etc
   Category: math
```

## How Tools Work

### User Query

```
User: "What is 2+2 and what's the weather in NY?"
```

### Agent Processing

1. **Agent reads query** → "I need to calculate and get weather"
2. **Agent looks at available tools** → calculator, search_internet, weather
3. **Agent decides** → "Use calculator for math, weather tool for NY"
4. **Agent executes tools** → Gets results from both
5. **Agent synthesizes** → Returns combined answer

### Why This Architecture?

**Traditional:**

- Add tool → Modify agent.py
- Agent imports grow
- Hard to maintain

**Our Way:**

- Add tool → Create new file in tools/
- Agent never changes
- Easy to scale

## Examples Included

### Enabled by Default

- **SearchTool** (`search.py`) - Internet search

### Available Examples (in `tools/examples.py`)

- **CalculatorTool** - Math operations
- **TimeTool** - Date/time info
- **TextAnalyzerTool** - Text statistics
- **EnvironmentCheckerTool** - Check env vars

To enable, uncomment the import in `tools/__init__.py`:

```python
# tools/__init__.py
from .examples import CalculatorTool, TimeTool, ...

__all__ = [
    "BaseTool",
    "ToolConfig",
    "ToolRegistry",
    "SearchTool",
    "CalculatorTool",
    "TimeTool",
    ...
]
```

Then run:

```bash
python app.py --list-tools
```

All example tools appear!

## Using Tools

### List All Tools

```bash
python app.py --list-tools
```

### Use Specific Tools

```bash
# Only search
python app.py -t "search_internet"

# Multiple tools
python app.py -t "search_internet,calculator,weather"

# Interactive with specific tools
python app.py -t "calculator,time" -i
```

### Single Query

```bash
python app.py -q "What is 5*5?"
# Agent uses calculator tool automatically
```

### Python API

```python
from agent import create_search_agent

# All tools
agent = create_search_agent()

# Specific tools
agent = create_search_agent(enabled_tools=["search_internet"])

response = agent.answer("What's the capital of France?")
print(response)
```

## Tool Development Pattern

Every tool follows the same pattern:

```python
from tools.base import BaseTool, ToolConfig
from langchain_core.tools import Tool


class MyNewTool(BaseTool):
    """One-line description"""

    def get_config(self) -> ToolConfig:
        """Define tool metadata"""
        return ToolConfig(
            name="unique_name",
            description="What this tool does",
            enabled=True,
            category="category"
        )

    def execute(self) -> Tool:
        """Create and return the tool"""
        def my_function(input_text: str) -> str:
            # Implementation
            return "result"

        return Tool(
            name="my_tool_name",
            func=my_function,
            description="What tool does"
        )

    def validate_config(self) -> bool:
        """Optional: Check if tool is properly configured"""
        return True
```

Copy this template for every new tool.

## Next Steps - What You Can Add

### Easy to Add:

- **Calculator** (done in examples.py)
- **Time/Date** (done in examples.py)
- **Text Analysis** (done in examples.py)

### Medium Complexity:

- **Web Scraper** (template in web_scraper_example.py)
- **File Reader** (read text files)
- **Code Executor** (run Python/shell)

### Advanced:

- **Database Query** (SQL, NoSQL)
- **API Integration** (REST APIs)
- **Email** (send/read emails)
- **Memory/Vector DB** (persistent memory)

**Each is just a new file implementing BaseTool!**

## Key Concepts

### BaseTool Interface

All tools must inherit from this class. Provides:

- `get_config()` - Tool metadata
- `execute()` - Return LangChain Tool
- `validate_config()` - Optional config validation

### ToolRegistry

Auto-discovers and loads all tools:

- Scans `tools/` directory
- Finds BaseTool subclasses
- Creates LangChain tools
- Manages lifecycle

### ToolConfig

Describes tool to agent:

- `name` - Unique identifier
- `description` - What tool does (LLM reads)
- `enabled` - On/off
- `category` - Organization
- `requires_api_key` - Optional dependency

### Agent Integration

Agent gets tools from registry:

- Doesn't hardcode any tools
- Uses ToolConfig descriptions
- Lets LLM decide which to use
- Works with any number of tools

## Development Workflow

1. **Create tool file** - `tools/my_tool.py`
2. **Implement BaseTool** - `get_config()`, `execute()`
3. **Export tool** - Add to `tools/__init__.py` (optional but recommended)
4. **Test tool** - Run `python app.py --list-tools`
5. **Use tool** - Agent auto-loads and uses it

## Verification

### Syntax Check

```bash
python -m py_compile tools/*.py agent.py
```

### List Tools

```bash
python app.py --list-tools
```

### Test Tool

```python
from tools.my_tool import MyTool
tool = MyTool()
print(tool.validate_config())
result = tool.execute().func("test")
print(result)
```

## Documentation

- **ARCHITECTURE.md** - Detailed tool development guide
- **TOOLS_GUIDE.md** - Tool development patterns and examples
- **tools/examples.py** - Working example implementations
- **tools/base.py** - BaseTool interface with docstrings
- **tools/registry.py** - ToolRegistry with documentation

## Summary

You now have:

✅ **Scalable Architecture** - Add features without touching core code  
✅ **Auto-Discovery System** - Tools load automatically  
✅ **Clear Interface** - BaseTool defines what all tools must do  
✅ **Working Example** - SearchTool already implemented  
✅ **Example Templates** - Copy/modify for new tools  
✅ **Comprehensive Docs** - Multiple guides and examples

**To add a new feature:**

1. Create file in `tools/`
2. Implement BaseTool
3. Done - tool auto-loads!

**The agent scales with you as requirements grow.**
