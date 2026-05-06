"""
Phase 8: Hardening & Production Readiness

Rate Limiting, Cost Controls, Circuit Breaker, Audit Trail, Notifications, Secret Management
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from core.database import SessionLocal
from core.models.agent_log import AgentLog, AgentType, AgentLogStatus
from core.models.task import Task, TaskStatus
from core.models.feature import Feature
from core.config import settings


class RateLimiter:
    """
    Rate limiting for capability gaps.

    Prevents runaway spending by limiting new gap tasks per day.
    """

    @staticmethod
    def get_daily_gap_count(db: Session, hours: int = 24) -> int:
        """
        Get count of capability gap tasks created in the last N hours.

        Args:
            db: Database session
            hours: Time window in hours (default 24)

        Returns:
            Count of gap detection logs in time window
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        count = (
            db.query(func.count(AgentLog.id))
            .filter(
                AgentLog.agent_type == AgentType.QUERY,
                AgentLog.action == "gap_detected",
                AgentLog.created_at >= cutoff,
            )
            .scalar()
        )
        return count or 0

    @staticmethod
    def is_rate_limited(
        db: Session,
        daily_limit: int = 10,
        hours: int = 24,
    ) -> tuple[bool, dict]:
        """
        Check if gap detection is rate-limited.

        Args:
            db: Database session
            daily_limit: Max gaps per day (from settings)
            hours: Time window in hours

        Returns:
            (is_limited: bool, info: dict with count and remaining)
        """
        count = RateLimiter.get_daily_gap_count(db, hours)
        is_limited = count >= daily_limit
        remaining = max(0, daily_limit - count)

        return (
            is_limited,
            {
                "current_count": count,
                "daily_limit": daily_limit,
                "remaining": remaining,
                "window_hours": hours,
            },
        )

    @staticmethod
    def log_gap_detection_attempt(
        db: Session,
        gap_description: str,
        allowed: bool,
        reason: Optional[str] = None,
    ) -> dict:
        """
        Log a capability gap detection attempt (success or rate-limited).

        Args:
            db: Database session
            gap_description: Description of the gap
            allowed: Whether the gap was allowed (True) or rejected (False)
            reason: Optional reason if rejected

        Returns:
            {success: bool, status: str}
        """
        try:
            action = "gap_detected" if allowed else "gap_rate_limited"
            status = AgentLogStatus.SUCCESS if allowed else AgentLogStatus.FAILURE

            log_entry = AgentLog(
                agent_type=AgentType.QUERY,
                action=action,
                details={
                    "gap_description": gap_description,
                    "allowed": allowed,
                    "reason": reason,
                },
                status=status,
                error_message=reason if not allowed else None,
            )
            db.add(log_entry)
            db.commit()

            return {"success": True, "status": "logged"}

        except Exception as exc:
            db.rollback()
            return {"success": False, "error": str(exc)}


class CostController:
    """
    Token budget & cost controls for agent runs.

    Tracks token usage and alerts on overuse.
    """

    @staticmethod
    def record_token_usage(
        db: Session,
        agent_type: AgentType,
        task_id: Optional[str],
        tokens_used: int,
        action: str,
    ) -> dict:
        """
        Record token usage for an agent action.

        Args:
            db: Database session
            agent_type: Type of agent (query, coding, testing, etc.)
            task_id: Associated task ID (if any)
            tokens_used: Number of tokens consumed
            action: Action performed

        Returns:
            {success: bool, tokens_used: int, budget_remaining?: int}
        """
        try:
            log_entry = AgentLog(
                agent_type=agent_type,
                task_id=task_id,
                action=action,
                details={
                    "tokens_used": tokens_used,
                    "cost_usd": round(tokens_used * 0.00002, 4),  # Rough estimate
                },
                status=AgentLogStatus.SUCCESS,
            )
            db.add(log_entry)
            db.commit()

            # Get total tokens used today
            daily_total = CostController.get_daily_token_usage(db)
            budget_remaining = max(
                0,
                settings.daily_token_budget - daily_total
            )

            return {
                "success": True,
                "tokens_used": tokens_used,
                "daily_total": daily_total,
                "budget_remaining": budget_remaining,
            }

        except Exception as exc:
            db.rollback()
            return {"success": False, "error": str(exc)}

    @staticmethod
    def get_daily_token_usage(db: Session, hours: int = 24) -> int:
        """
        Get total tokens used in the last N hours.

        Args:
            db: Database session
            hours: Time window in hours

        Returns:
            Total tokens used
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        logs = (
            db.query(AgentLog)
            .filter(
                AgentLog.created_at >= cutoff,
                AgentLog.status == AgentLogStatus.SUCCESS,
            )
            .all()
        )

        total_tokens = 0
        for log in logs:
            if log.details and isinstance(log.details, dict):
                total_tokens += log.details.get("tokens_used", 0)

        return total_tokens

    @staticmethod
    def is_over_budget(db: Session) -> tuple[bool, dict]:
        """
        Check if daily token budget is exceeded.

        Args:
            db: Database session

        Returns:
            (is_over: bool, info: dict with usage and budget)
        """
        daily_usage = CostController.get_daily_token_usage(db)
        budget = settings.daily_token_budget
        is_over = daily_usage >= budget

        return (
            is_over,
            {
                "daily_usage": daily_usage,
                "daily_budget": budget,
                "percent_used": round((daily_usage / budget * 100) if budget > 0 else 0, 2),
            },
        )


class CircuitBreaker:
    """
    Agent circuit breaker: auto-escalate after N failures on same task.

    Prevents infinite retry loops and escal
ates to human when agent fails repeatedly.
    """

    @staticmethod
    def get_failure_count(db: Session, task_id: str) -> int:
        """
        Get number of failures for a task.

        Counts both patch failures and test failures on same task.

        Args:
            db: Database session
            task_id: Task ID to check

        Returns:
            Number of failures
        """
        failure_actions = [
            "patch_and_retry_error",
            "run_tests_failed",
            "create_pr_failed",
        ]

        count = (
            db.query(func.count(AgentLog.id))
            .filter(
                AgentLog.task_id == task_id,
                AgentLog.action.in_(failure_actions),
            )
            .scalar()
        )
        return count or 0

    @staticmethod
    def should_escalate(
        db: Session,
        task_id: str,
        failure_threshold: int = 3,
    ) -> tuple[bool, dict]:
        """
        Check if task should be escalated to human (circuit open).

        Args:
            db: Database session
            task_id: Task ID to check
            failure_threshold: Number of failures before escalation

        Returns:
            (should_escalate: bool, info: dict with failure count and reason)
        """
        failure_count = CircuitBreaker.get_failure_count(db, task_id)
        should_escalate = failure_count >= failure_threshold

        return (
            should_escalate,
            {
                "failure_count": failure_count,
                "threshold": failure_threshold,
                "reason": f"Agent failed {failure_count} times on this task"
                if should_escalate
                else None,
            },
        )

    @staticmethod
    def escalate_task(db: Session, task_id: str, reason: str) -> dict:
        """
        Escalate a task to human review (set status to ESCALATED).

        Args:
            db: Database session
            task_id: Task ID to escalate
            reason: Reason for escalation

        Returns:
            {success: bool, task_id: str, status: str}
        """
        try:
            task = (
                db.query(Task)
                .filter(Task.id == task_id)
                .first()
            )

            if not task:
                return {"success": False, "error": "Task not found"}

            task.status = TaskStatus.ESCALATED
            task.escalation_reason = reason

            log_entry = AgentLog(
                agent_type=AgentType.CODING,
                task_id=task_id,
                action="circuit_breaker_escalation",
                details={
                    "reason": reason,
                    "failure_count": CircuitBreaker.get_failure_count(db, task_id),
                },
                status=AgentLogStatus.FAILURE,
                error_message=reason,
            )
            db.add(log_entry)
            db.commit()

            return {
                "success": True,
                "task_id": str(task_id),
                "status": "escalated",
                "reason": reason,
            }

        except Exception as exc:
            db.rollback()
            return {"success": False, "error": str(exc)}


# Convenient factory functions
def get_rate_limiter() -> RateLimiter:
    """Get RateLimiter instance."""
    return RateLimiter()


def get_cost_controller() -> CostController:
    """Get CostController instance."""
    return CostController()


def get_circuit_breaker() -> CircuitBreaker:
    """Get CircuitBreaker instance."""
    return CircuitBreaker()
