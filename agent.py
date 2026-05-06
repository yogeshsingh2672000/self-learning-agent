"""
LangChain agent for question answering with pluggable tools.
Uses a scalable tool registry system for easy feature additions.
"""
import os
from typing import Optional, List
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent

from constants import PROVIDERS
from tools import ToolRegistry


class SearchAgent:
    """
    Scalable LangChain agent with pluggable tools.
    
    Features:
    - Uses ToolRegistry for dynamic tool loading
    - Easy to add new tools (no agent code changes needed)
    - Autonomous decision-making about tool usage
    - Conversation history support
    
    Example:
        agent = SearchAgent()
        response = agent.answer("What's the latest AI news?")
        print(response)
    """
    
    def __init__(
        self,
        llm_provider: str = "openai",
        temperature: float = 0.7,
        verbose: bool = False,
        enabled_tools: List[str] = None
    ):
        """
        Initialize the scalable agent.
        
        Args:
            llm_provider: LLM provider (openai)
            temperature: Temperature for LLM generation
            verbose: Enable verbose logging
            enabled_tools: List of tool names to enable (None = enable all)
        """
        self.llm_provider = llm_provider
        self.verbose = verbose
        
        # Initialize LLM
        self.llm = self._initialize_llm(llm_provider, temperature)
        
        # Initialize tool registry (dynamically loads tools)
        self.tool_registry = ToolRegistry(enabled_tools=enabled_tools)
        
        # Initialize agent with tools
        self.agent_executor = self._create_agent()
    
    def _initialize_llm(self, provider: str, temperature: float):
        """Initialize the LLM based on provider type"""
        if provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY not set in environment")
            
            model = os.getenv("OPENAI_MODEL", "gpt-4")
            return ChatOpenAI(
                api_key=api_key,
                model=model,
                temperature=temperature,
                streaming=False
            )
        else:
            raise NotImplementedError(
                f"LangChain integration for {provider} not yet implemented. "
                "Currently only OpenAI is supported."
            )
    
    def _create_agent(self):
        """
        Create the LangChain agent with dynamic tools.
        Uses the new create_agent API (LangChain 1.x / LangGraph-based).
        Tools are loaded from the ToolRegistry.
        """
        
        # Get all available tools from registry
        tools = self.tool_registry.get_langchain_tools()
        
        if not tools:
            raise ValueError("No tools available. Check tool registry.")
        
        # Build system prompt
        system_prompt = """You are a helpful AI assistant with access to various tools.

You have the following tools available:"""
        
        available_tools = self.tool_registry.get_available_tools()
        for tool_name, config in available_tools.items():
            system_prompt += f"\n- {config.name}: {config.description}"
        
        system_prompt += """

When answering questions:
1. Use appropriate tools to find information when needed
2. Always cite your sources when using tool results
3. Provide clear, comprehensive answers
4. If using tools, wait for results before answering

Be conversational and helpful."""
        
        # create_agent returns a CompiledStateGraph (LangGraph)
        return create_agent(
            model=self.llm,
            tools=tools,
            system_prompt=system_prompt,
        )
    
    def answer(self, query: str, chat_history: Optional[List] = None) -> str:
        """
        Answer a user query using the agent
        
        Args:
            query: User's question
            chat_history: Previous conversation messages (optional)
        
        Returns:
            Agent's response
        """
        try:
            # Build messages list with optional chat history
            messages = list(chat_history or [])
            messages.append(HumanMessage(content=query))
            
            # Run the agent (new LangGraph-based API)
            response = self.agent_executor.invoke({"messages": messages})
            
            # Extract the last AI message from the response
            response_messages = response.get("messages", [])
            for msg in reversed(response_messages):
                if isinstance(msg, AIMessage) and msg.content:
                    return msg.content
            return "No response generated"
        except Exception as e:
            return f"Error: {str(e)}"
    
    def run_interactive(self):
        """Run the agent in interactive mode"""
        print("\n" + "=" * 70)
        print("SEARCH AGENT - Interactive Mode")
        print("=" * 70)
        print(f"LLM Provider: {self.llm_provider}")
        print("\nType your questions below. Type 'exit' to quit.\n")
        
        chat_history = []
        
        while True:
            try:
                user_input = input("You: ").strip()
                
                if user_input.lower() in ["exit", "quit", "q"]:
                    print("\nGoodbye!")
                    break
                
                if not user_input:
                    continue
                
                print("\nAgent is thinking...\n")
                response = self.answer(user_input, chat_history)
                print(f"Agent: {response}\n")
                
                # Update chat history
                chat_history.append(HumanMessage(content=user_input))
                chat_history.append(AIMessage(content=response))
                
            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break
            except Exception as e:
                print(f"Error: {e}\n")


def create_search_agent(
    llm_provider: str = "openai",
    enabled_tools: List[str] = None,
    **kwargs
) -> SearchAgent:
    """
    Factory function to create a scalable search agent.
    
    Args:
        llm_provider: LLM provider (openai)
        enabled_tools: List of tool names to enable (None = enable all)
        **kwargs: Additional arguments for SearchAgent
    
    Returns:
        Initialized SearchAgent instance
    
    Example:
        # Create with all available tools
        agent = create_search_agent()
        
        # Create with specific tools only
        agent = create_search_agent(enabled_tools=["search_internet"])
    """
    return SearchAgent(
        llm_provider=llm_provider,
        enabled_tools=enabled_tools,
        **kwargs
    )
