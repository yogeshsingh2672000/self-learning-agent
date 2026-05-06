"""
Phase 8: Audit Trail & Hardening Endpoints

Endpoints for:
- Querying agent decision logs
- Cost/token usage reporting
- Rate limit status
- Circuit breaker status
"""
from typing import Optional, List
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, func

from core.database import get_db
from core.models import AgentLog, Task, TaskStatus, AgentType, AgentLogStatus
from core.hardening import RateLimiter, CostController, CircuitBreaker
from core.config import settings
from api.deps import get_current_user

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ── Audit Trail Endpoints ────────────────────────────────────────────────────

@router.get("/audit-trail")
def get_audit_trail(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
    task_id: Optional[str] = Query(None, description="Filter by task ID"),
    agent_type: Optional[str] = Query(None, description="Filter by agent type (query, coding, testing)"),
    status: Optional[str] = Query(None, description="Filter by status (success, failure, in_progress)"),
    action: Optional[str] = Query(None, description="Filter by action name"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict:
    """
    Query audit trail of agent decisions and actions.

    Returns paginated list of agent_log entries with filters.

    Args:
        task_id: Optional UUID of a specific task
        agent_type: Filter by agent type
        status: Filter by action status
        action: Filter by action name pattern
        limit: Number of results per page
        offset: Pagination offset

    Returns:
        {
            total: int,
            limit: int,
            offset: int,
            logs: [
                {id, agent_type, task_id, action, status, created_at, details, error_message}
            ]
        }
    """
    # Build query
    query = db.query(AgentLog)

    if task_id:
        try:
            query = query.filter(AgentLog.task_id == UUID(task_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid task_id format")

    if agent_type:
        query = query.filter(AgentLog.agent_type == agent_type)

    if status:
        query = query.filter(AgentLog.status == status)

    if action:
        query = query.filter(AgentLog.action.ilike(f"%{action}%"))

    # Get total count
    total = query.count()

    # Apply pagination and sorting
    logs = (
        query
        .order_by(desc(AgentLog.created_at))
        .limit(limit)
        .offset(offset)
        .all()
    )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "logs": [
            {
                "id": str(log.id),
                "agent_type": log.agent_type,
                "task_id": str(log.task_id) if log.task_id else None,
                "action": log.action,
                "status": log.status,
                "created_at": log.created_at.isoformat(),
                "details": log.details or {},
                "error_message": log.error_message,
            }
            for log in logs
        ],
    }


@router.get("/audit-trail/{task_id}")
def get_task_audit_trail(
    task_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
) -> dict:
    """
    Get complete audit trail for a specific task.

    Returns all agent_log entries for the task in chronological order.

    Args:
        task_id: Task UUID

    Returns:
        {
            task_id: str,
            task_title: str,
            task_status: str,
            logs: [AgentLog...]
        }
    """
    try:
        task_uuid = UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task_id format")

    task = db.query(Task).filter(Task.id == task_uuid).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    logs = (
        db.query(AgentLog)
        .filter(AgentLog.task_id == task_uuid)
        .order_by(AgentLog.created_at)
        .all()
    )

    return {
        "task_id": str(task.id),
        "task_title": task.title,
        "task_status": task.status,
        "logs": [
            {
                "id": str(log.id),
                "agent_type": log.agent_type,
                "action": log.action,
                "status": log.status,
                "created_at": log.created_at.isoformat(),
                "details": log.details or {},
                "error_message": log.error_message,
            }
            for log in logs
        ],
    }


# ── Cost Control Endpoints ───────────────────────────────────────────────────

@router.get("/cost-tracking")
def get_cost_tracking(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
    hours: int = Query(24, ge=1, le=720, description="Time window in hours"),
) -> dict:
    """
    Get token usage and cost tracking for the time window.

    Args:
        hours: Time window in hours (1-720, default 24)

    Returns:
        {
            window_hours: int,
            daily_budget: int,
            tokens_used: int,
            percent_used: float,
            cost_usd: float,
            is_over_budget: bool,
            breakdown: {agent_type: {tokens: int, cost: float}}
        }
    """
    daily_usage = CostController.get_daily_token_usage(db, hours)
    budget = settings.daily_token_budget
    percent_used = (daily_usage / budget * 100) if budget > 0 else 0

    # Cost estimate: roughly $0.00002 per token (varies by model)
    cost_usd = round(daily_usage * 0.00002, 4)

    # Breakdown by agent type
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    logs = (
        db.query(
            AgentLog.agent_type,
            func.sum(
                func.cast(
                    func.json_extract_path_text(
                        AgentLog.details,
                        "tokens_used"
                    ),
                    'INTEGER'
                )
            ).label("total_tokens")
        )
        .filter(
            AgentLog.created_at >= cutoff,
            AgentLog.status == AgentLogStatus.SUCCESS,
        )
        .group_by(AgentLog.agent_type)
        .all()
    )

    breakdown = {}
    for agent_type, tokens in logs:
        if agent_type and tokens:
            breakdown[agent_type] = {
                "tokens": int(tokens),
                "cost_usd": round(int(tokens) * 0.00002, 4),
            }

    return {
        "window_hours": hours,
        "daily_budget": budget,
        "tokens_used": daily_usage,
        "percent_used": round(percent_used, 2),
        "cost_usd": cost_usd,
        "is_over_budget": daily_usage >= budget,
        "breakdown": breakdown,
    }


@router.get("/rate-limiting")
def get_rate_limiting(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
) -> dict:
    """
    Get current rate limiting status.

    Returns:
        {
            daily_limit: int,
            current_count: int,
            remaining: int,
            window_hours: int,
            is_limited: bool,
            reset_at: str (ISO format)
        }
    """
    is_limited, limit_info = RateLimiter.is_rate_limited(
        db,
        daily_limit=settings.daily_gap_limit,
        hours=settings.gap_rate_limit_hours,
    )

    # Calculate reset time (end of 24-hour window from earliest log)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.gap_rate_limit_hours)
    earliest_log = (
        db.query(AgentLog.created_at)
        .filter(
            AgentLog.agent_type == AgentType.QUERY,
            AgentLog.action == "gap_detected",
            AgentLog.created_at >= cutoff,
        )
        .order_by(AgentLog.created_at)
        .first()
    )

    reset_at = None
    if earliest_log:
        reset_at = (
            earliest_log[0] + timedelta(hours=settings.gap_rate_limit_hours)
        ).isoformat()

    return {
        "daily_limit": limit_info["daily_limit"],
        "current_count": limit_info["current_count"],
        "remaining": limit_info["remaining"],
        "window_hours": limit_info["window_hours"],
        "is_limited": is_limited,
        "reset_at": reset_at,
    }


# ── Circuit Breaker Status ───────────────────────────────────────────────────

@router.get("/circuit-breaker/{task_id}")
def get_circuit_breaker_status(
    task_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
) -> dict:
    """
    Get circuit breaker status for a task.

    Args:
        task_id: Task UUID

    Returns:
        {
            task_id: str,
            failure_count: int,
            failure_threshold: int,
            should_escalate: bool,
            reason: str | None
        }
    """
    try:
        task_uuid = UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task_id format")

    should_escalate, circuit_info = CircuitBreaker.should_escalate(
        db,
        str(task_uuid),
        failure_threshold=settings.failure_threshold,
    )

    return {
        "task_id": str(task_uuid),
        "failure_count": circuit_info["failure_count"],
        "failure_threshold": circuit_info["threshold"],
        "should_escalate": should_escalate,
        "reason": circuit_info.get("reason"),
    }


# ── Escalation Summary ───────────────────────────────────────────────────────

@router.get("/escalations")
def get_escalations(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
    status: Optional[str] = Query("escalated", description="Filter by task status"),
    limit: int = Query(50, ge=1, le=500),
) -> dict:
    """
    Get list of escalated tasks.

    Args:
        status: Task status filter (default: escalated)
        limit: Max results

    Returns:
        {
            total: int,
            tasks: [
                {id, title, status, escalation_reason, escalated_at, failure_count}
            ]
        }
    """
    query = db.query(Task)

    if status:
        query = query.filter(Task.status == status)

    tasks = query.order_by(desc(Task.created_at)).limit(limit).all()
    total = query.count()

    result = []
    for task in tasks:
        failure_count = CircuitBreaker.get_failure_count(db, str(task.id))
        result.append({
            "id": str(task.id),
            "title": task.title,
            "status": task.status,
            "escalation_reason": task.escalation_reason,
            "escalated_at": task.updated_at.isoformat() if task.updated_at else None,
            "failure_count": failure_count,
        })

    return {
        "total": total,
        "tasks": result,
    }


# ── Daily Report ─────────────────────────────────────────────────────────────

@router.get("/daily-report")
def get_daily_report(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
) -> dict:
    """
    Get daily summary report for all Phase 8 metrics.

    Returns:
        {
            date: str,
            tasks: {pending_approval, approved, in_development, testing, in_review, deployed, escalated},
            costs: {tokens_used, budget_remaining, cost_usd, percent_used},
            rate_limit: {current_count, remaining, is_limited},
            circuit_breaker: {escalations_count, failure_threshold},
            notifications: {pr_created, deployments, escalations}
        }
    """
    db_session = db

    # Task counts
    task_statuses = {}
    for status in TaskStatus:
        count = (
            db_session.query(func.count(Task.id))
            .filter(Task.status == status)
            .scalar()
        )
        task_statuses[status] = count or 0

    # Cost tracking
    is_over, cost_info = CostController.is_over_budget(db_session)
    daily_usage = CostController.get_daily_token_usage(db_session)

    # Rate limiting
    is_limited, limit_info = RateLimiter.is_rate_limited(
        db_session,
        daily_limit=settings.daily_gap_limit,
    )

    # Escalations today
    escalations_count = (
        db_session.query(func.count(AgentLog.id))
        .filter(
            AgentLog.action == "circuit_breaker_escalation",
            AgentLog.created_at >= datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            ),
        )
        .scalar()
    )

    # Notifications sent (from logs)
    notifications_sent = (
        db_session.query(func.count(AgentLog.id))
        .filter(
            AgentLog.action.in_([
                "create_pr_success",
                "pr_merged_webhook",
                "task_escalated",
            ]),
            AgentLog.created_at >= datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            ),
        )
        .scalar()
    )

    return {
        "date": datetime.now(timezone.utc).date().isoformat(),
        "tasks": task_statuses,
        "costs": {
            "tokens_used": daily_usage,
            "budget_remaining": max(0, settings.daily_token_budget - daily_usage),
            "cost_usd": round(daily_usage * 0.00002, 4),
            "percent_used": round(cost_info.get("percent_used", 0), 2),
            "is_over_budget": is_over,
        },
        "rate_limit": {
            "current_count": limit_info["current_count"],
            "remaining": limit_info["remaining"],
            "is_limited": is_limited,
        },
        "circuit_breaker": {
            "escalations_count": escalations_count or 0,
            "failure_threshold": settings.failure_threshold,
        },
        "notifications": {
            "sent_today": notifications_sent or 0,
        },
    }
