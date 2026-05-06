"""
Main application entry point - Scalable LangChain agent.
Demonstrates an agent with pluggable tool system.
Also serves as ASGI entry point for uvicorn.
"""
import asyncio
import argparse

# Import settings first to load .env file
from core.config import settings

# ── FastAPI App (for uvicorn) ──────────────────────────────────────────────────
from api.main import app  # Export for uvicorn: uvicorn app:app --reload

from agent import create_search_agent
from tools import ToolRegistry


async def main():
    """Main application"""
    parser = argparse.ArgumentParser(
        description="Scalable AI Agent - Ask questions and use available tools"
    )
    parser.add_argument(
        "-q", "--query",
        type=str,
        help="Single query to answer and exit"
    )
    parser.add_argument(
        "-l", "--llm",
        type=str,
        default="openai",
        help="LLM provider (openai)"
    )
    parser.add_argument(
        "-t", "--tools",
        type=str,
        help="Comma-separated list of tools to enable (e.g., 'search_internet')"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Run in interactive mode"
    )
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="List all available tools and exit"
    )
    
    args = parser.parse_args()
    
    # If user requested tool list, show and exit
    if args.list_tools:
        registry = ToolRegistry()
        registry.print_tools_info()
        return
    
    # Banner
    print("\n" + "=" * 70)
    print(" " * 15 + "SCALABLE AI AGENT")
    print("=" * 70)
    print(f"LLM Provider: {args.llm}")
    
    # Parse enabled tools
    enabled_tools = None
    if args.tools:
        enabled_tools = [t.strip() for t in args.tools.split(",")]
        print(f"Tools: {', '.join(enabled_tools)}")
    else:
        print("Tools: All available tools enabled")
    
    print("=" * 70 + "\n")
    
    # Create agent
    try:
        agent = create_search_agent(
            llm_provider=args.llm,
            temperature=0.7,
            verbose=args.verbose,
            enabled_tools=enabled_tools
        )
    except Exception as e:
        print(f"Error initializing agent: {e}")
        return
    
    # Run query or interactive mode
    if args.query:
        # Single query mode
        print(f"Query: {args.query}\n")
        response = agent.answer(args.query)
        print(f"Answer:\n{response}\n")
    elif args.interactive:
        # Interactive mode
        agent.run_interactive()
    else:
        # Default: run in interactive mode
        agent.run_interactive()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
    except Exception as e:
        print(f"\nError: {e}")
