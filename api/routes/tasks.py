"""
Tasks routes — Phase 3 full implementation.

Endpoints:
  GET    /api/tasks                   — list tasks with optional status filter + pagination
  GET    /api/tasks/{id}              — get task detail
  POST   /api/tasks                   — create task (manual)
  PATCH  /api/tasks/{id}/approve      — approve a pending task
  PATCH  /api/tasks/{id}/reject       — reject a pending task
  POST   /api/tasks/{id}/vote         — upvote a task
  POST   /api/tasks/process           — run Task Manager Agent on a pending task
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.deps import get_current_user, get_current_admin
from core.database import get_db
from core.models.user import User
from core.models.task import Task, TaskStatus
from core.models.approval_log import ApprovalLog, ApprovalDecision
from core.models.agent_log import AgentLog, AgentType, AgentLogStatus

router = APIRouter()


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class TaskCreateRequest(BaseModel):
    title: str
    description: str
    acceptance_criteria: Optional[list[str]] = None
    required_capabilities: Optional[list[str]] = None


class TaskApproveRequest(BaseModel):
    comment: Optional[str] = None


class TaskRejectRequest(BaseModel):
    comment: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _task_to_dict(task: Task) -> dict:
    criteria = task.acceptance_criteria
    if criteria and isinstance(criteria, str):
        try:
            criteria = json.loads(criteria)
        except Exception:
            criteria = [criteria]

    return {
        "id": str(task.id),
        "title": task.title,
        "description": task.description,
        "status": task.status.value,
        "priority_score": task.priority_score,
        "acceptance_criteria": criteria or [],
        "vote_count": task.vote_count,
        "requested_by": task.requested_by,
        "required_capabilities": task.required_capabilities or [],
        "approved_at": task.approved_at.isoformat() if task.approved_at else None,
        "deployed_at": task.deployed_at.isoformat() if task.deployed_at else None,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }


def _log_agent_action(
    db: Session,
    action: str,
    task_id: Optional[uuid.UUID],
    details: Optional[dict],
    log_status: AgentLogStatus = AgentLogStatus.SUCCESS,
    error: Optional[str] = None,
) -> None:
    entry = AgentLog(
        agent_type=AgentType.TASK_MANAGER,
        task_id=task_id,
        action=action,
        details=details,
        status=log_status,
        error_message=error,
    )
    db.add(entry)


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("", summary="List tasks with optional status filter")
def list_tasks(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
    task_status: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    q = db.query(Task)

    if task_status:
        try:
            ts = TaskStatus(task_status)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status. Valid values: {[s.value for s in TaskStatus]}",
            )
        q = q.filter(Task.status == ts)

    total = q.count()
    tasks = q.order_by(Task.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "tasks": [_task_to_dict(t) for t in tasks],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{task_id}", summary="Get task detail")
def get_task(
    task_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    try:
        tid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID")

    task = db.query(Task).filter(Task.id == tid).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return _task_to_dict(task)


@router.post("", status_code=status.HTTP_201_CREATED, summary="Manually create a task")
def create_task(
    body: TaskCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    task = Task(
        title=body.title,
        description=body.description,
        acceptance_criteria=json.dumps(body.acceptance_criteria or []),
        required_capabilities=body.required_capabilities or [],
        requested_by=current_user.email,
        status=TaskStatus.PENDING_APPROVAL,
    )
    db.add(task)
    db.flush()

    _log_agent_action(
        db,
        action="task_created_manually",
        task_id=task.id,
        details={"title": body.title, "requested_by": current_user.email},
    )

    db.commit()
    db.refresh(task)
    return _task_to_dict(task)


@router.patch("/{task_id}/approve", summary="Approve a pending task")
def approve_task(
    task_id: str,
    body: TaskApproveRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    try:
        tid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID")

    task = db.query(Task).filter(Task.id == tid).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status not in (TaskStatus.PENDING_APPROVAL,):
        raise HTTPException(
            status_code=400,
            detail=f"Task is not pending approval (current status: {task.status.value})",
        )

    task.status = TaskStatus.APPROVED
    task.approved_at = datetime.now(timezone.utc)

    approval = ApprovalLog(
        task_id=task.id,
        approver=current_user.email,
        decision=ApprovalDecision.APPROVED,
        comment=body.comment,
    )
    db.add(approval)

    _log_agent_action(
        db,
        action="task_approved",
        task_id=task.id,
        details={"approver": current_user.email, "comment": body.comment},
    )

    db.commit()
    db.refresh(task)
    return _task_to_dict(task)


@router.patch("/{task_id}/reject", summary="Reject a pending task")
def reject_task(
    task_id: str,
    body: TaskRejectRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    try:
        tid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID")

    task = db.query(Task).filter(Task.id == tid).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status not in (TaskStatus.PENDING_APPROVAL,):
        raise HTTPException(
            status_code=400,
            detail=f"Task is not pending approval (current status: {task.status.value})",
        )

    task.status = TaskStatus.REJECTED

    rejection = ApprovalLog(
        task_id=task.id,
        approver=current_user.email,
        decision=ApprovalDecision.REJECTED,
        comment=body.comment,
    )
    db.add(rejection)

    _log_agent_action(
        db,
        action="task_rejected",
        task_id=task.id,
        details={"approver": current_user.email, "comment": body.comment},
    )

    db.commit()
    db.refresh(task)
    return _task_to_dict(task)


@router.post("/{task_id}/vote", summary="Upvote a task")
def vote_task(
    task_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    try:
        tid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID")

    task = db.query(Task).filter(Task.id == tid).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status == TaskStatus.REJECTED:
        raise HTTPException(status_code=400, detail="Cannot vote on a rejected task")

    task.vote_count = (task.vote_count or 0) + 1

    _log_agent_action(
        db,
        action="task_upvoted",
        task_id=task.id,
        details={"voter": current_user.email, "new_vote_count": task.vote_count},
    )

    db.commit()
    db.refresh(task)
    return {"vote_count": task.vote_count, "task_id": str(task.id)}


@router.post("/process", summary="Run Task Manager Agent to enrich a task")
def process_task(
    task_id: str = Query(..., description="UUID of the task to process"),
    current_user: Annotated[User, Depends(get_current_user)] = None,
    db: Session = Depends(get_db),
):
    """
    Runs the Task Manager Agent pipeline on an existing task:
    - Deduplication check against other pending tasks
    - Priority scoring
    - Acceptance criteria generation

    On duplicate: marks task as rejected and links to the original.
    On success: updates task with priority_score and acceptance_criteria.
    """
    from agents.task_manager_agent import get_task_manager_agent

    try:
        tid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID")

    task = db.query(Task).filter(Task.id == tid).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Gather existing pending tasks for dedup (exclude the current task)
    existing = db.query(Task).filter(
        Task.id != tid,
        Task.status.in_([TaskStatus.PENDING_APPROVAL, TaskStatus.APPROVED]),
    ).all()

    existing_dicts = [
        {"id": str(t.id), "title": t.title, "description": t.description}
        for t in existing
    ]

    try:
        agent = get_task_manager_agent()
        result = agent.process_task(
            title=task.title,
            description=task.description,
            requested_by=task.requested_by or current_user.email,
            required_capabilities=task.required_capabilities,
            existing_tasks=existing_dicts,
            current_vote_count=task.vote_count or 0,
        )
    except Exception as e:
        _log_agent_action(
            db,
            action="task_processing_failed",
            task_id=task.id,
            details={"error": str(e)},
            log_status=AgentLogStatus.FAILURE,
            error=str(e),
        )
        db.commit()
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")

    if result["is_duplicate"]:
        task.status = TaskStatus.REJECTED
        _log_agent_action(
            db,
            action="task_deduplicated",
            task_id=task.id,
            details={"duplicate_of": result["duplicate_id"]},
        )
        db.commit()
        db.refresh(task)
        return {
            "processed": True,
            "is_duplicate": True,
            "duplicate_id": result["duplicate_id"],
            "task": _task_to_dict(task),
        }

    # Apply enrichment
    task.priority_score = result["priority_score"]
    task.acceptance_criteria = result["acceptance_criteria"]
    task.required_capabilities = result["required_capabilities"]
    # Add rationale + effort to description
    if result.get("rationale"):
        task.description = (
            task.description
            + f"\n\n**Priority rationale:** {result['rationale']}"
            + f"\n**Estimated effort:** {result['estimated_effort']}"
        )

    _log_agent_action(
        db,
        action="task_enriched",
        task_id=task.id,
        details={
            "priority_score": result["priority_score"],
            "estimated_effort": result.get("estimated_effort"),
        },
    )

    db.commit()
    db.refresh(task)
    return {
        "processed": True,
        "is_duplicate": False,
        "task": _task_to_dict(task),
    }
