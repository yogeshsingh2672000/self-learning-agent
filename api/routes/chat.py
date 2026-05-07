"""
Chat API routes for Query Agent interactions.

Endpoints:
- POST /api/chat - Send a message to the Query Agent
- GET /api/chat/history - Get conversation history
- GET /api/chat/sessions - List conversation sessions
"""
from typing import List, Optional
from uuid import UUID
from datetime import datetime
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.deps import get_current_user
from core.database import get_db
from core.models import User, ChatHistory, MessageRole, Task, TaskStatus
from agents.query_agent import create_query_agent

# Set up logging
logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatMessageRequest:
    """Request body for chat messages"""
    def __init__(self, message: str, session_id: Optional[str] = None):
        self.message = message
        self.session_id = session_id


class ChatMessageResponse:
    """Response from chat message"""
    def __init__(
        self,
        id: str,
        message: str,
        role: str,
        timestamp: datetime,
        task_created: Optional[dict] = None
    ):
        self.id = id
        self.message = message
        self.role = role
        self.timestamp = timestamp
        self.task_created = task_created


class ChatHistoryResponse:
    """Single chat history entry"""
    def __init__(self, history: ChatHistory):
        self.id = str(history.id)
        self.role = history.role.value
        self.message = history.message
        self.timestamp = history.message_timestamp
        self.is_capability_gap = history.is_capability_gap
        self.gap_description = history.gap_description
        self.suggested_tool = history.suggested_tool
        self.task_id = str(history.task_id) if history.task_id else None


# Create query agent instance (will be reused for all requests)
# In production, consider using dependency injection or a singleton pattern
query_agent = None

def get_query_agent():
    """Get or create the Query Agent"""
    global query_agent
    if query_agent is None:
        query_agent = create_query_agent(
            llm_provider="openai",
            detect_gaps=True,
            verbose=False
        )
    return query_agent


@router.post("/", response_model=dict)
async def send_message(
    message: str,
    session_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> dict:
    """
    Send a message to the Query Agent.
    
    Returns:
    - agent_response: The agent's answer
    - gap_detected: Whether a capability gap was detected
    - task_created: Task details if a gap was detected and task created
    - session_id: Session ID for this conversation
    - message_id: ID of the stored message
    """
    try:
        # Validate input
        if not message or not message.strip():
            raise HTTPException(status_code=400, detail="Message cannot be empty")
        
        message = message.strip()
        
        # Use provided session_id or create a new one
        if not session_id:
            session_id = str(current_user.id)  # Use user ID as default session
        
        # Fetch conversation history for this session
        history_records = db.query(ChatHistory).filter(
            ChatHistory.user_id == current_user.id,
            ChatHistory.session_id == session_id
        ).order_by(ChatHistory.message_timestamp).all()
        
        # Convert to LangChain message format
        from langchain_core.messages import HumanMessage, AIMessage
        chat_history = []
        for record in history_records[-20:]:  # Last 20 messages only
            if record.role == MessageRole.USER:
                chat_history.append(HumanMessage(content=record.message))
            elif record.role == MessageRole.AGENT:
                chat_history.append(AIMessage(content=record.message))
        
        # Get query agent
        agent = get_query_agent()
        
        # Get agent response
        result = agent.answer(
            query=message,
            chat_history=chat_history,
            session_id=session_id
        )
        
        # Store user message
        user_message = ChatHistory(
            user_id=current_user.id,
            session_id=session_id,
            role=MessageRole.USER,
            message=message,
            message_timestamp=datetime.utcnow()
        )
        db.add(user_message)
        db.flush()  # Flush to get the ID
        
        # Store agent response
        agent_message = ChatHistory(
            user_id=current_user.id,
            session_id=session_id,
            role=MessageRole.AGENT,
            message=result['answer'],
            is_capability_gap=result['gap_detected'],
            gap_description=result['gap_info'].get('gap_description') if result['gap_info'] else None,
            suggested_tool=result['gap_info'].get('suggested_tool') if result['gap_info'] else None,
            message_timestamp=datetime.utcnow()
        )
        db.add(agent_message)
        db.flush()
        
        # Create task if gap detected
        task_created = None
        if result['gap_detected'] and result['gap_info']:
            # Generate task from gap
            task_data = {
                "title": f"Implement {result['gap_info'].get('suggested_tool', 'new feature')} tool",
                "description": f"User asked: \"{message}\"\n\nWhy needed: {result['gap_info'].get('gap_description', 'To answer user queries')}",
                "status": TaskStatus.PENDING_APPROVAL,
                "requested_by": str(current_user.id),
                "required_capabilities": [result['gap_info'].get('suggested_tool')] if result['gap_info'].get('suggested_tool') else [],
                "acceptance_criteria": f"Implement {result['gap_info'].get('suggested_tool', 'new feature')}\nAdd documentation\nAdd unit tests\nIntegrate with existing tools"
            }
            
            # Create task
            new_task = Task(**task_data)
            db.add(new_task)
            db.flush()
            
            # Link task to agent message
            agent_message.task_id = new_task.id
            
            task_created = {
                "id": str(new_task.id),
                "title": new_task.title,
                "status": new_task.status.value,
                "created_at": new_task.created_at.isoformat()
            }
        
        db.commit()
        
        return {
            "agent_response": result['answer'],
            "gap_detected": result['gap_detected'],
            "task_created": task_created,
            "session_id": session_id,
            "user_message_id": str(user_message.id),
            "agent_message_id": str(agent_message.id),
            "timestamp": datetime.utcnow().isoformat()
        }
    
    except Exception as e:
        db.rollback()
        # Log the full error for debugging
        logger.error(f"Chat error: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing message: {str(e)}")


@router.get("/history", response_model=dict)
async def get_chat_history(
    session_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> dict:
    """
    Get conversation history for the current user.
    
    Query Parameters:
    - session_id: Optional session ID to filter by (defaults to user's main session)
    - limit: Number of messages to return (max 500)
    - offset: Number of messages to skip
    
    Returns:
    - messages: List of chat messages
    - total: Total number of messages in the session
    - session_id: The session ID
    """
    try:
        if not session_id:
            session_id = str(current_user.id)
        
        # Get total count
        total = db.query(ChatHistory).filter(
            ChatHistory.user_id == current_user.id,
            ChatHistory.session_id == session_id
        ).count()
        
        # Get paginated results
        messages = db.query(ChatHistory).filter(
            ChatHistory.user_id == current_user.id,
            ChatHistory.session_id == session_id
        ).order_by(ChatHistory.message_timestamp.desc()).offset(offset).limit(limit).all()
        
        # Reverse to show oldest first
        messages = list(reversed(messages))
        
        return {
            "messages": [
                {
                    "id": str(msg.id),
                    "role": msg.role.value,
                    "message": msg.message,
                    "timestamp": msg.message_timestamp.isoformat(),
                    "is_capability_gap": msg.is_capability_gap,
                    "gap_description": msg.gap_description,
                    "suggested_tool": msg.suggested_tool,
                    "task_id": str(msg.task_id) if msg.task_id else None
                }
                for msg in messages
            ],
            "total": total,
            "session_id": session_id,
            "limit": limit,
            "offset": offset
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving history: {str(e)}")


@router.get("/sessions", response_model=dict)
async def get_chat_sessions(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> dict:
    """
    Get all chat sessions for the current user.
    
    Returns:
    - sessions: List of sessions with message counts
    - total: Total number of sessions
    """
    try:
        # Get distinct sessions
        from sqlalchemy import func
        sessions = db.query(
            ChatHistory.session_id,
            func.count(ChatHistory.id).label('message_count'),
            func.max(ChatHistory.message_timestamp).label('last_message')
        ).filter(
            ChatHistory.user_id == current_user.id
        ).group_by(ChatHistory.session_id).order_by(
            func.max(ChatHistory.message_timestamp).desc()
        ).limit(limit).all()
        
        return {
            "sessions": [
                {
                    "session_id": session[0],
                    "message_count": session[1],
                    "last_message": session[2].isoformat() if session[2] else None
                }
                for session in sessions
            ],
            "total": len(sessions)
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving sessions: {str(e)}")


@router.delete("/{message_id}")
async def delete_message(
    message_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> dict:
    """Delete a chat message (user messages only)"""
    try:
        message_uuid = UUID(message_id)
        
        # Find and delete message
        message = db.query(ChatHistory).filter(
            ChatHistory.id == message_uuid,
            ChatHistory.user_id == current_user.id,
            ChatHistory.role == MessageRole.USER
        ).first()
        
        if not message:
            raise HTTPException(status_code=404, detail="Message not found or cannot be deleted")
        
        db.delete(message)
        db.commit()
        
        return {"message": "Message deleted successfully"}
    
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid message ID")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting message: {str(e)}")
