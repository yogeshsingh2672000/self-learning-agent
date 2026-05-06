"""
Example Tools - Multiple patterns and use cases

These are example tools showing different patterns for creating tools.
Uncomment and import in tools/__init__.py to use them.
"""

from langchain_core.tools import Tool
import os
import re
from tools.base import BaseTool, ToolConfig


# ============================================================================
# 1. CALCULATOR TOOL - Simple math operations
# ============================================================================

class CalculatorTool(BaseTool):
    """
    Calculator tool - Perform mathematical calculations.
    Simple example with error handling.
    """
    
    def get_config(self) -> ToolConfig:
        return ToolConfig(
            name="calculator",
            description="Perform mathematical calculations. "
                       "Input: math expression (e.g., '2 + 2', 'sqrt(16)', 'sin(0)')",
            enabled=True,
            category="math"
        )
    
    def execute(self) -> Tool:
        def calculate(expression: str) -> str:
            """Safe math evaluation with limited scope"""
            try:
                # Only allow safe math operations
                import math
                allowed_names = {
                    'sqrt': math.sqrt,
                    'sin': math.sin,
                    'cos': math.cos,
                    'tan': math.tan,
                    'log': math.log,
                    'exp': math.exp,
                    'pi': math.pi,
                    'e': math.e,
                }
                
                result = eval(expression, {"__builtins__": {}}, allowed_names)
                return f"Result: {result}"
            except ZeroDivisionError:
                return "Error: Division by zero"
            except ValueError as e:
                return f"Error: Invalid value - {str(e)}"
            except NameError as e:
                return f"Error: Unknown function - {str(e)}"
            except Exception as e:
                return f"Error: {type(e).__name__}: {str(e)}"
        
        return Tool(
            name="calculator",
            func=calculate,
            description="Perform mathematical calculations"
        )


# ============================================================================
# 2. TIME TOOL - Get current time and date info
# ============================================================================

class TimeTool(BaseTool):
    """
    Time tool - Get current time, date, timezone info.
    No API keys or external dependencies needed.
    """
    
    def get_config(self) -> ToolConfig:
        return ToolConfig(
            name="get_time",
            description="Get current date and time information. "
                       "Input: timezone (e.g., 'UTC', 'EST') or 'local' for local time",
            enabled=True,
            category="information"
        )
    
    def execute(self) -> Tool:
        def get_time(timezone: str = "local") -> str:
            """Get current time in specified timezone"""
            try:
                from datetime import datetime
                import pytz
                
                if timezone.lower() == "local":
                    now = datetime.now()
                    return f"Local time: {now.strftime('%Y-%m-%d %H:%M:%S')}"
                else:
                    tz = pytz.timezone(timezone)
                    now = datetime.now(tz)
                    return f"Time in {timezone}: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}"
            except Exception as e:
                return f"Error: {str(e)}. Use timezone like 'UTC', 'US/Eastern', etc."
        
        return Tool(
            name="get_time",
            func=get_time,
            description="Get current date and time"
        )


# ============================================================================
# 3. TEXT ANALYSIS TOOL - Analyze text content
# ============================================================================

class TextAnalyzerTool(BaseTool):
    """
    Text analysis tool - Analyze text for statistics and patterns.
    Shows how to process and analyze data.
    """
    
    def get_config(self) -> ToolConfig:
        return ToolConfig(
            name="analyze_text",
            description="Analyze text for word count, character count, "
                       "sentence count, and average word length. "
                       "Input: text to analyze",
            enabled=True,
            category="utility"
        )
    
    def execute(self) -> Tool:
        def analyze_text(text: str) -> str:
            """Analyze text statistics"""
            try:
                # Word count
                words = text.split()
                word_count = len(words)
                
                # Character count
                char_count = len(text)
                
                # Sentence count (simple)
                sentences = re.split(r'[.!?]+', text)
                sentence_count = len([s for s in sentences if s.strip()])
                
                # Average word length
                avg_word_length = (
                    sum(len(w) for w in words) / word_count
                    if word_count > 0 else 0
                )
                
                return f"""Text Analysis:
- Words: {word_count}
- Characters: {char_count}
- Sentences: {sentence_count}
- Avg word length: {avg_word_length:.2f}"""
            except Exception as e:
                return f"Error: {str(e)}"
        
        return Tool(
            name="analyze_text",
            func=analyze_text,
            description="Analyze text for word count, characters, and statistics"
        )


# ============================================================================
# 4. ENVIRONMENT CHECKER TOOL - Check environment variables
# ============================================================================

class EnvironmentCheckerTool(BaseTool):
    """
    Environment checker tool - Check if required API keys are set.
    Useful for debugging tool availability.
    """
    
    def get_config(self) -> ToolConfig:
        return ToolConfig(
            name="check_environment",
            description="Check if specified environment variables are set. "
                       "Input: comma-separated variable names "
                       "(e.g., 'OPENAI_API_KEY,MY_API_KEY')",
            enabled=True,
            category="utility"
        )
    
    def execute(self) -> Tool:
        def check_environment(var_names: str) -> str:
            """Check if environment variables are set"""
            try:
                variables = [v.strip() for v in var_names.split(",")]
                result = "Environment variables status:\n"
                
                for var in variables:
                    is_set = bool(os.getenv(var))
                    status = "✓ Set" if is_set else "✗ Not set"
                    result += f"- {var}: {status}\n"
                
                return result
            except Exception as e:
                return f"Error: {str(e)}"
        
        return Tool(
            name="check_environment",
            func=check_environment,
            description="Check if environment variables are set"
        )


# ============================================================================
# HOW TO USE THESE EXAMPLES
# ============================================================================
#
# 1. To enable a single tool, add to tools/__init__.py:
#
#    from .examples import CalculatorTool
#    __all__ = [..., "CalculatorTool"]
#
# 2. To enable multiple tools, add all imports and exports:
#
#    from .examples import (
#        CalculatorTool,
#        TimeTool,
#        TextAnalyzerTool,
#        EnvironmentCheckerTool
#    )
#    __all__ = [..., "CalculatorTool", "TimeTool", "TextAnalyzerTool", ...]
#
# 3. Run to see available tools:
#
#    python app.py --list-tools
#
# 4. Use in agent:
#
#    python app.py -q "What is 2+2?"
#    # Agent will use calculator tool
#
#    python app.py -q "Get current time in UTC"
#    # Agent will use time tool
#
# ============================================================================
