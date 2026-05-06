"""
Query Agent - The user-facing agent that answers questions and detects capability gaps.

This agent:
1. Processes user queries using available tools
2. Detects when it can't answer properly (capability gap)
3. Suggests new tools/features to close the gap
4. Stores gaps as tasks for human approval
"""
import os
import json
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent

from core.config import settings
from constants import PROVIDERS
from tools import ToolRegistry


class CapabilityGapDetector:
    """
    Detects when the Query Agent couldn't answer a question properly.
    
    Uses LLM to evaluate if the answer was sufficient, and if not,
    suggests what tool/capability would help answer the question.
    """
    
    def __init__(self, llm: ChatOpenAI):
        """Initialize with an LLM instance"""
        self.llm = llm
    
    def evaluate_gap(
        self,
        query: str,
        response: str,
        used_tools: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Evaluate if the response was sufficient, and detect gaps.
        
        Args:
            query: The original user query
            response: The agent's response
            used_tools: Tools that were used in generating the response
        
        Returns:
            Dict with:
            - is_gap: bool - Whether a capability gap was detected
            - gap_description: str - Description of what the agent couldn't do
            - suggested_tool: str - What tool/capability would help
            - confidence: float - Confidence in the gap detection (0-1)
        """
        gap_evaluation_prompt = f"""Analyze this interaction:

USER QUERY: {query}

AGENT RESPONSE: {response}

TOOLS USED: {', '.join(used_tools) if used_tools else 'None'}

Your task:
1. Is the response sufficient to answer the user's query? (yes/no)
2. If no, what tool or capability is missing?
3. How confident are you in this assessment? (0-1)

Return a JSON object with:
{{
    "is_gap": boolean,
    "gap_description": "what the agent couldn't do",
    "suggested_tool": "what tool/capability would help or null",
    "confidence": 0.0-1.0
}}

Only return valid JSON, no other text."""
        
        try:
            messages = [HumanMessage(content=gap_evaluation_prompt)]
            response = self.llm.invoke(messages)
            
            # Parse the JSON response
            content = response.content.strip()
            # Remove markdown code blocks if present
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            
            result = json.loads(content)
            return result
        except Exception as e:
            # On error, return a safe default
            return {
                "is_gap": False,
                "gap_description": None,
                "suggested_tool": None,
                "confidence": 0.0
            }
    
    def generate_task_from_gap(
        self,
        gap_info: Dict[str, Any],
        original_query: str
    ) -> Dict[str, Any]:
        """
        Generate a task specification from a detected capability gap.
        
        Args:
            gap_info: Output from evaluate_gap()
            original_query: The original user query that revealed the gap
        
        Returns:
            Task dict ready to be saved to the database
        """
        # Generate acceptance criteria using LLM
        criteria_prompt = f"""A user asked: "{original_query}"

The system couldn't answer because: {gap_info['gap_description']}

The suggested tool to implement: {gap_info['suggested_tool']}

Generate 3-5 concise acceptance criteria for this feature. 
Return as a JSON array of strings.
Only return valid JSON, no other text."""
        
        try:
            messages = [HumanMessage(content=criteria_prompt)]
            response = self.llm.invoke(messages)
            
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            
            criteria = json.loads(content)
        except Exception:
            criteria = [
                f"Implement {gap_info['suggested_tool']} tool",
                "Add documentation",
                "Add unit tests",
                "Verify integration with existing tools"
            ]
        
        return {
            "title": f"Implement {gap_info['suggested_tool']} tool",
            "description": f"User asked: \"{original_query}\"\n\nWhy needed: {gap_info['gap_description']}",
            "acceptance_criteria": json.dumps(criteria),
            "requested_by": "query_agent",
            "required_capabilities": [gap_info['suggested_tool']],
            "gap_source_query": original_query,
        }


class QueryAgent:
    """
    The user-facing Query Agent.
    
    Responsibilities:
    - Answer user questions using available tools
    - Detect when it can't answer (capability gaps)
    - Auto-create tasks for capability gaps
    - Store conversation history
    
    Features:
    - Uses ToolRegistry for dynamic tool loading
    - Easy to add new tools (no agent code changes needed)
    - Autonomous decision-making about tool usage
    - Conversation history support
    - Capability gap detection
    """
    
    def __init__(
        self,
        llm_provider: str = "openai",
        temperature: float = 0.7,
        verbose: bool = False,
        enabled_tools: List[str] = None,
        detect_gaps: bool = True
    ):
        """
        Initialize the Query Agent.
        
        Args:
            llm_provider: LLM provider (openai)
            temperature: Temperature for LLM generation
            verbose: Enable verbose logging
            enabled_tools: List of tool names to enable (None = enable all)
            detect_gaps: Whether to detect and report capability gaps
        """
        self.llm_provider = llm_provider
        self.verbose = verbose
        self.detect_gaps = detect_gaps
        
        # Initialize LLM
        self.llm = self._initialize_llm(llm_provider, temperature)
        
        # Initialize tool registry
        self.tool_registry = ToolRegistry(enabled_tools=enabled_tools)
        
        # Initialize capability gap detector
        self.gap_detector = CapabilityGapDetector(self.llm)
        
        # Initialize agent executor
        self.agent_executor = self._create_agent()
    
    def _initialize_llm(self, provider: str, temperature: float):
        """Initialize the LLM based on provider type"""
        if provider == "openai":
            if not settings.openai_api_key:
                raise ValueError("OPENAI_API_KEY not set in .env file")
            
            return ChatOpenAI(
                api_key=settings.openai_api_key,
                model=settings.openai_model,
                temperature=temperature,
                streaming=False
            )
        else:
            raise NotImplementedError(
                f"LLM provider {provider} not yet implemented. "
                "Currently only OpenAI is supported."
            )
    
    def _create_agent(self):
        """
        Create the LangChain agent with dynamic tools.
        Uses the new create_agent API (LangChain 1.x / LangGraph-based).
        """
        
        # Get all available tools from registry
        tools = self.tool_registry.get_langchain_tools()
        
        if not tools:
            raise ValueError("No tools available. Check tool registry.")
        
        # Build system prompt
        system_prompt = """You are a helpful AI assistant designed to answer user questions.

You have access to the following tools:"""
        
        available_tools = self.tool_registry.get_available_tools()
        for tool_name, config in available_tools.items():
            system_prompt += f"\n- {config.name}: {config.description}"
        
        system_prompt += """

Instructions:
1. Use tools to find accurate information when needed
2. Always cite your sources when using tool results
3. Provide clear, comprehensive answers
4. If a tool doesn't exist for a query, explain what you would need
5. Be conversational and helpful
6. If uncertain, ask clarifying questions"""
        
        # Create agent
        return create_agent(
            model=self.llm,
            tools=tools,
            system_prompt=system_prompt,
        )
    
    def answer(
        self,
        query: str,
        chat_history: Optional[List] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Answer a user query and detect capability gaps.
        
        Args:
            query: User's question
            chat_history: Previous conversation messages (optional)
            session_id: Conversation session ID for tracking
        
        Returns:
            Dict with:
            - answer: str - Agent's response
            - gap_detected: bool - Whether a capability gap was found
            - gap_info: dict - Details about the gap (if detected)
            - tools_used: list - Tools that were used
            - session_id: str - Session ID for this conversation
        """
        try:
            # Build messages list
            messages = list(chat_history or [])
            messages.append(HumanMessage(content=query))
            
            # Run the agent
            response = self.agent_executor.invoke({"messages": messages})
            
            # Extract the last AI message
            response_messages = response.get("messages", [])
            agent_response = None
            tools_used = []
            
            for msg in reversed(response_messages):
                if isinstance(msg, AIMessage) and msg.content:
                    agent_response = msg.content
                    break
            
            if not agent_response:
                agent_response = "No response generated"
            
            # Detect capability gaps if enabled
            gap_detected = False
            gap_info = None
            
            if self.detect_gaps:
                gap_evaluation = self.gap_detector.evaluate_gap(
                    query=query,
                    response=agent_response,
                    used_tools=tools_used
                )
                
                if gap_evaluation.get("is_gap", False) and gap_evaluation.get("confidence", 0) > 0.6:
                    gap_detected = True
                    gap_info = gap_evaluation
            
            return {
                "answer": agent_response,
                "gap_detected": gap_detected,
                "gap_info": gap_info,
                "tools_used": tools_used,
                "session_id": session_id or str(uuid.uuid4()),
                "timestamp": datetime.utcnow().isoformat()
            }
        
        except Exception as e:
            return {
                "answer": f"Error: {str(e)}",
                "gap_detected": False,
                "gap_info": None,
                "tools_used": [],
                "session_id": session_id or str(uuid.uuid4()),
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(e)
            }
    
    def run_interactive(self):
        """Run the agent in interactive mode"""
        print("\n" + "=" * 70)
        print("QUERY AGENT - Interactive Mode")
        print("=" * 70)
        print(f"LLM Provider: {self.llm_provider}")
        print("Gap Detection: " + ("Enabled" if self.detect_gaps else "Disabled"))
        print("\nType your questions below. Type 'exit' to quit.\n")
        
        chat_history = []
        session_id = str(uuid.uuid4())
        
        while True:
            try:
                user_input = input("You: ").strip()
                
                if user_input.lower() in ["exit", "quit", "q"]:
                    print("\nGoodbye!")
                    break
                
                if not user_input:
                    continue
                
                print("\nAgent is thinking...\n")
                result = self.answer(user_input, chat_history, session_id)
                
                print(f"Agent: {result['answer']}\n")
                
                if result['gap_detected']:
                    print(f"⚠️  Capability Gap Detected:")
                    print(f"   Gap: {result['gap_info']['gap_description']}")
                    print(f"   Suggested Tool: {result['gap_info']['suggested_tool']}")
                    print(f"   Confidence: {result['gap_info']['confidence']:.1%}\n")
                
                # Update chat history
                chat_history.append(HumanMessage(content=user_input))
                chat_history.append(AIMessage(content=result['answer']))
                
            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break
            except Exception as e:
                print(f"Error: {e}\n")


def create_query_agent(
    llm_provider: str = "openai",
    enabled_tools: List[str] = None,
    detect_gaps: bool = True,
    **kwargs
) -> QueryAgent:
    """
    Factory function to create a Query Agent.
    
    Args:
        llm_provider: LLM provider (openai)
        enabled_tools: List of tool names to enable (None = enable all)
        detect_gaps: Whether to detect capability gaps
        **kwargs: Additional arguments for QueryAgent
    
    Returns:
        Initialized QueryAgent instance
    
    Example:
        # Create with all available tools and gap detection
        agent = create_query_agent()
    """
    return QueryAgent(
        llm_provider=llm_provider,
        enabled_tools=enabled_tools,
        detect_gaps=detect_gaps,
        **kwargs
    )
