"""
Tasks routes — Phase 3 + Phase 5 full implementation.

Endpoints:
  GET    /api/tasks                        — list tasks with optional status filter + pagination
  GET    /api/tasks/{id}                   — get task detail
  POST   /api/tasks                        — create task (manual)
  PATCH  /api/tasks/{id}/approve           — approve a pending task
  PATCH  /api/tasks/{id}/reject            — reject a pending task
  POST   /api/tasks/{id}/vote              — upvote a task
  POST   /api/tasks/process                — run Task Manager Agent on a pending task
  GET    /api/tasks/{id}/execution-log     — Phase 4: live agent execution log
  GET    /api/tasks/{id}/test-results      — Phase 5: latest test results + bug report
  POST   /webhooks/github                  — Phase 6: GitHub PR webhook handler
  GET    /api/tasks/{id}/pr-status         — Phase 6: PR status and metadata
"""
import json
import uuid
import hmac
import hashlib
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.deps import get_current_user, get_current_admin
from core.config import settings
from core.database import get_db
from core.models.user import User
from core.models.task import Task, TaskStatus
from core.models.feature import Feature, FeatureStatus
from core.models.approval_log import ApprovalLog, ApprovalDecision
from core.models.agent_log import AgentLog, AgentType, AgentLogStatus
from workers.tasks import generate_tool_code, handle_pr_approved, handle_pr_merged

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

    # Trigger Celery task to generate code (Phase 4)
    generate_tool_code.delay(str(task.id))

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


@router.get("/{task_id}/execution-log", summary="Get agent execution log for a task")
def get_execution_log(
    task_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """
    Get all agent execution logs (AgentLog entries) for a task.

    Used to show live progress during code generation, testing, etc.

    Returns:
        {
            "logs": [
                {
                    "id": str,
                    "agent_type": str,  # "query"|"task_manager"|"coding"|"testing"
                    "action": str,      # "generate_tool_code_started", "generate_tool_code_success", etc.
                    "status": str,      # "success"|"failure"|"in_progress"
                    "details": dict,
                    "error_message": str | null,
                    "timestamp": str,
                }
            ],
            "total": int,
            "limit": int,
            "offset": int,
            "task_status": str,
        }
    """
    try:
        tid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID")

    task = db.query(Task).filter(Task.id == tid).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Fetch logs
    logs_query = db.query(AgentLog).filter(AgentLog.task_id == tid)
    total = logs_query.count()
    logs = logs_query.order_by(AgentLog.created_at.asc()).offset(offset).limit(limit).all()

    return {
        "logs": [
            {
                "id": str(log.id),
                "agent_type": log.agent_type.value,
                "action": log.action,
                "status": log.status.value,
                "details": log.details or {},
                "error_message": log.error_message,
                "timestamp": log.created_at.isoformat(),
            }
            for log in logs
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
        "task_status": task.status.value,
    }


@router.get("/{task_id}/test-results", summary="Get latest test results for a task (Phase 5)")
def get_test_results(
    task_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    """
    Return the latest test execution results for a task, including:
    - Coverage percentage
    - Per-test pass/fail outcomes
    - Bug report (when tests failed)
    - Retry count and escalation status

    Returns:
        {
            "task_id":        str,
            "task_status":    str,
            "escalation_reason": str | null,
            "feature": {
                "id":               str,
                "branch_name":      str | null,
                "tool_name":        str | null,
                "status":           str,
                "retry_count":      int,
                "test_results": {
                    "passed":           bool,
                    "total":            int,
                    "passed_count":     int,
                    "failed_count":     int,
                    "coverage_percent": float,
                    "tests": [{name, outcome, duration, message}],
                    "bug_report":       dict | null,
                    "stdout":           str,
                    "stderr":           str,
                } | null,
            } | null
        }
    """
    try:
        tid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID")

    task = db.query(Task).filter(Task.id == tid).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Fetch the most recent Feature for this task
    feature = (
        db.query(Feature)
        .filter(Feature.task_id == tid)
        .order_by(Feature.created_at.desc())
        .first()
    )

    feature_payload = None
    if feature:
        tr = feature.test_results  # already a dict (JSON column)
        feature_payload = {
            "id": str(feature.id),
            "branch_name": feature.branch_name,
            "tool_name": feature.tool_name,
            "status": feature.status.value,
            "retry_count": feature.retry_count,
            "test_results": tr if tr else None,
        }

    return {
        "task_id": str(task.id),
        "task_status": task.status.value,
        "escalation_reason": task.escalation_reason if hasattr(task, "escalation_reason") else None,
        "feature": feature_payload,
    }


@router.post("/webhooks/github", summary="GitHub webhook handler (Phase 6)")
async def github_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    GitHub webhook handler for PR approval and merge events.

    Verifies X-Hub-Signature-256 header, then processes:
    - pull_request.approved → task.status = PENDING_DEPLOYMENT
    - pull_request.merged → task.status = DEPLOYED, feature.status = DEPLOYED

    Requires github_webhook_secret in .env
    """
    # Verify webhook signature
    signature_header = request.headers.get("X-Hub-Signature-256")
    if not signature_header or not settings.github_webhook_secret:
        raise HTTPException(status_code=401, detail="Unauthorized")

    body = await request.body()
    expected_sig = (
        "sha256="
        + hmac.new(
            settings.github_webhook_secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
    )

    if not hmac.compare_digest(signature_header, expected_sig):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = json.loads(body)
    action = payload.get("action", "")
    pr = payload.get("pull_request", {})
    pr_number = pr.get("number")

    # Try to find task by matching PR head branch to feature.branch_name
    # Branch format: feature/agent/{task_id[:8]}-{tool_name}
    if not pr_number:
        return {"ok": False, "message": "No PR number in payload"}

    head_ref = pr.get("head", {}).get("ref", "")
    if not head_ref.startswith("feature/agent/"):
        return {"ok": False, "message": "Not an agent-generated branch"}

    # Extract task_id from branch name
    try:
        task_id_short = head_ref.split("/")[-1].split("-")[0]
        # Find feature with matching branch and task
        feature = (
            db.query(Feature)
            .filter(Feature.branch_name == head_ref)
            .order_by(Feature.created_at.desc())
            .first()
        )

        if not feature:
            return {"ok": False, "message": "Feature branch not found"}

        task_id = str(feature.task_id)

        if action == "submitted" and payload.get("review", {}).get("state") == "approved":
            # PR was approved
            handle_pr_approved.delay(task_id, pr_number)
            return {"ok": True, "action": "pr_approved"}

        elif action == "closed" and pr.get("merged"):
            # PR was merged
            handle_pr_merged.delay(task_id, pr_number)
            return {"ok": True, "action": "pr_merged"}

        else:
            return {"ok": True, "action": "ignored", "reason": f"action={action}"}

    except Exception as exc:
        return {
            "ok": False,
            "message": f"Error processing webhook: {str(exc)}",
        }


@router.get("/{task_id}/pr-status", summary="Get PR status for a task (Phase 6)")
def get_pr_status(
    task_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    """
    Return PR metadata for a task.

    Returns PR URL, PR number, PR status, and merged status.
    """
    try:
        tid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID")

    task = db.query(Task).filter(Task.id == tid).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Get the most recent feature (which has the PR link)
    feature = (
        db.query(Feature)
        .filter(Feature.task_id == tid)
        .order_by(Feature.created_at.desc())
        .first()
    )

    if not feature or not feature.pr_url:
        return {
            "task_id": str(task.id),
            "pr_url": None,
            "pr_number": None,
            "pr_status": None,
            "merged": False,
        }

    return {
        "task_id": str(task.id),
        "pr_url": feature.pr_url,
        "pr_number": feature.pr_number,
        "pr_status": feature.pr_status,
        "merged": feature.pr_status == "merged",
    }

