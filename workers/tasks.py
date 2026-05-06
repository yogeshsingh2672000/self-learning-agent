"""
Background task definitions.

Phase 4: generate_tool_code — triggered when a task is APPROVED
Phase 5: run_tests           — triggered when code generation succeeds
         patch_and_retry     — triggered when tests fail (≤3 attempts)
Phase 6: handle_pr_approved, handle_pr_merged — GitHub webhook handlers
Phase 8: Rate limiting, cost controls, circuit breaker, notifications
"""
import json
import uuid
from datetime import datetime, timezone

from workers.celery_app import celery_app
from core.database import SessionLocal
from core.models import Task, TaskStatus, Feature, FeatureStatus, AgentLog, AgentType, AgentLogStatus
from core.hardening import RateLimiter, CostController, CircuitBreaker
from core.notifications import NotificationService
from core.config import settings
from agents.coding_agent import get_coding_agent


@celery_app.task(name="workers.tasks.worker_health_check", bind=True)
def worker_health_check(self) -> dict:
    """Verify the Celery worker is running and reachable."""
    return {"status": "worker healthy", "task_id": self.request.id}


@celery_app.task(name="workers.tasks.generate_tool_code", bind=True, max_retries=2)
def generate_tool_code(self, task_id: str) -> dict:
    """
    Celery task: Generate tool code for an approved task.

    Triggered when a task transitions from PENDING_APPROVAL → APPROVED.
    
    Phase 8: Checks rate limiting before allowing code generation.

    Args:
        task_id: UUID of the task

    Returns:
        {"success": bool, "error": str | None, "details": dict}
    """
    db = SessionLocal()
    try:
        # Load task
        task = db.query(Task).filter(Task.id == uuid.UUID(task_id)).first()
        if not task:
            log_entry = AgentLog(
                agent_type=AgentType.CODING,
                task_id=None,
                action="generate_tool_code",
                details={"task_id": task_id, "error": "Task not found"},
                status=AgentLogStatus.FAILURE,
                error_message="Task not found",
            )
            db.add(log_entry)
            db.commit()
            return {"success": False, "error": "Task not found", "details": {}}

        # ── Phase 8: Check rate limiting ───────────────────────────
        is_limited, limit_info = RateLimiter.is_rate_limited(
            db,
            daily_limit=settings.daily_gap_limit,
            hours=settings.gap_rate_limit_hours,
        )

        if is_limited:
            task.status = TaskStatus.REJECTED
            rejection_msg = (
                f"Rate limit exceeded: {limit_info['current_count']} gaps created today "
                f"(limit: {limit_info['daily_limit']})"
            )

            log_entry = AgentLog(
                agent_type=AgentType.CODING,
                task_id=task.id,
                action="rate_limited",
                details={
                    "tool_name": task.title,
                    **limit_info,
                },
                status=AgentLogStatus.FAILURE,
                error_message=rejection_msg,
            )
            db.add(log_entry)
            db.commit()

            # Log the rate limit attempt
            RateLimiter.log_gap_detection_attempt(
                db, task.description or "", allowed=False, reason=rejection_msg
            )

            return {
                "success": False,
                "error": rejection_msg,
                "details": limit_info,
            }

        # Log allowed gap
        RateLimiter.log_gap_detection_attempt(
            db, task.description or "", allowed=True
        )

        # Log start
        log_entry = AgentLog(
            agent_type=AgentType.CODING,
            task_id=task.id,
            action="generate_tool_code_started",
            details={"tool_name": task.title},
            status=AgentLogStatus.IN_PROGRESS,
        )
        db.add(log_entry)
        db.commit()

        # Run agent
        agent = get_coding_agent()
        result = agent.generate_code(task)

        if result["success"]:
            # Create Feature record
            feature = Feature(
                task_id=task.id,
                branch_name=result["branch_name"],
                tool_name=result["tool_name"],
                status=FeatureStatus.DEVELOPMENT,
                retry_count=0,
            )
            db.add(feature)

            # Update task
            task.status = TaskStatus.IN_DEVELOPMENT

            # Log success
            log_entry = AgentLog(
                agent_type=AgentType.CODING,
                task_id=task.id,
                action="generate_tool_code_success",
                details={
                    "tool_name": result["tool_name"],
                    "branch_name": result["branch_name"],
                    "files_created": result["files_created"],
                },
                status=AgentLogStatus.SUCCESS,
            )
            db.add(log_entry)
            db.commit()

            # Refresh to get the new feature ID, then trigger Phase 5 testing
            db.refresh(feature)
            run_tests.delay(str(task.id), str(feature.id))

            return {
                "success": True,
                "error": None,
                "details": {
                    "tool_name": result["tool_name"],
                    "branch_name": result["branch_name"],
                    "files_created": result["files_created"],
                },
            }
        else:
            # Log failure
            log_entry = AgentLog(
                agent_type=AgentType.CODING,
                task_id=task.id,
                action="generate_tool_code_failed",
                details={"error": result["error"]},
                status=AgentLogStatus.FAILURE,
                error_message=result["error"],
            )
            db.add(log_entry)
            db.commit()

            return {"success": False, "error": result["error"], "details": {}}

    except Exception as e:
        # Log error and retry
        log_entry = AgentLog(
            agent_type=AgentType.CODING,
            task_id=uuid.UUID(task_id) if task_id else None,
            action="generate_tool_code_error",
            details={"error": str(e)},
            status=AgentLogStatus.FAILURE,
            error_message=str(e),
        )
        db.add(log_entry)
        db.commit()

        # Retry after 30 seconds
        self.retry(countdown=30, exc=e)
    finally:
        db.close()


# ── Phase 5 tasks ─────────────────────────────────────────────────────────────

MAX_RETRY_ATTEMPTS = 3


@celery_app.task(name="workers.tasks.run_tests", bind=True, max_retries=1)
def run_tests(self, task_id: str, feature_id: str) -> dict:
    """
    Celery task: Run Testing Agent on a feature branch.

    Triggered by generate_tool_code on success.
    Flow:
      PASS  → feature.status = IN_REVIEW, task.status = IN_REVIEW
      FAIL (retry_count < MAX) → patch_and_retry.delay(...)
      FAIL (retry_count >= MAX) → task.status = ESCALATED
    """
    from agents.testing_agent import get_testing_agent

    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == uuid.UUID(task_id)).first()
        feature = db.query(Feature).filter(Feature.id == uuid.UUID(feature_id)).first()

        if not task or not feature:
            return {"success": False, "error": "Task or Feature not found", "details": {}}

        # Update statuses to TESTING
        task.status = TaskStatus.TESTING
        feature.status = FeatureStatus.TESTING

        log_start = AgentLog(
            agent_type=AgentType.TESTING,
            task_id=task.id,
            action="run_tests_started",
            details={
                "tool_name": feature.tool_name,
                "branch_name": feature.branch_name,
                "attempt": feature.retry_count + 1,
            },
            status=AgentLogStatus.IN_PROGRESS,
        )
        db.add(log_start)
        db.commit()

        # Parse acceptance criteria
        criteria = task.acceptance_criteria
        if isinstance(criteria, str):
            try:
                criteria = json.loads(criteria)
            except Exception:
                criteria = [criteria] if criteria else []
        criteria = criteria or []

        tool_name = feature.tool_name or ""
        tool_class = "".join(w.capitalize() for w in tool_name.split("_"))

        # Run tests via Testing Agent
        agent = get_testing_agent()
        result = agent.run_tests(
            tool_name=tool_name,
            tool_class=tool_class,
            tool_description=task.description,
            acceptance_criteria=criteria,
            tool_code=feature.tool_code or "",
            test_code=feature.test_code or "",
        )

        test_results = result["test_results"]
        bug_report = result.get("bug_report")

        # Persist test results (include bug_report inside the JSON)
        combined_results = dict(test_results)
        if bug_report:
            combined_results["bug_report"] = bug_report

        feature.test_results = combined_results

        if result["passed"]:
            # ── Tests passed — create PR (Phase 6) ────────────────────
            feature.status = FeatureStatus.IN_REVIEW
            task.status = TaskStatus.IN_REVIEW

            log_ok = AgentLog(
                agent_type=AgentType.TESTING,
                task_id=task.id,
                action="run_tests_passed",
                details={
                    "tool_name": tool_name,
                    "total": test_results.get("total", 0),
                    "passed_count": test_results.get("passed_count", 0),
                    "coverage_percent": test_results.get("coverage_percent", 0.0),
                },
                status=AgentLogStatus.SUCCESS,
            )
            db.add(log_ok)
            db.commit()

            # Create PR via Coding Agent
            coding_agent = get_coding_agent()
            pr_result = coding_agent.create_pr(task, feature)

            if pr_result["success"]:
                feature.pr_url = pr_result["pr_url"]
                feature.pr_number = pr_result["pr_number"]
                feature.pr_status = "open"

                log_pr = AgentLog(
                    agent_type=AgentType.CODING,
                    task_id=task.id,
                    action="create_pr_success",
                    details={
                        "pr_number": pr_result["pr_number"],
                        "pr_url": pr_result["pr_url"],
                        "tool_name": tool_name,
                    },
                    status=AgentLogStatus.SUCCESS,
                )
                db.add(log_pr)

                # ── Phase 8: Send notification ─────────────────
                NotificationService.notify_pr_created(
                    str(task.id),
                    task.title,
                    pr_result["pr_url"],
                    pr_result["pr_number"]
                )
            else:
                log_pr_fail = AgentLog(
                    agent_type=AgentType.CODING,
                    task_id=task.id,
                    action="create_pr_failed",
                    details={"error": pr_result["error"]},
                    status=AgentLogStatus.FAILURE,
                    error_message=pr_result["error"],
                )
                db.add(log_pr_fail)

            db.commit()
            return {"success": True, "error": None, "details": {"status": "in_review", "pr_url": pr_result.get("pr_url")}}


        # ── Tests failed ──────────────────────────────────────────────
        feature.retry_count = (feature.retry_count or 0) + 1
        feature.status = FeatureStatus.FAILED

        log_fail = AgentLog(
            agent_type=AgentType.TESTING,
            task_id=task.id,
            action="run_tests_failed",
            details={
                "tool_name": tool_name,
                "total": test_results.get("total", 0),
                "failed_count": test_results.get("failed_count", 0),
                "retry_count": feature.retry_count,
                "bug_summary": bug_report.get("summary", "") if bug_report else "",
            },
            status=AgentLogStatus.FAILURE,
            error_message=bug_report.get("summary", "Tests failed") if bug_report else "Tests failed",
        )
        db.add(log_fail)
        db.commit()

        # ── Phase 8: Circuit breaker check ─────────────────────────
        should_escalate_now, circuit_info = CircuitBreaker.should_escalate(
            db,
            str(task.id),
            failure_threshold=settings.failure_threshold,
        )

        if should_escalate_now:
            # Circuit open - escalate immediately
            CircuitBreaker.escalate_task(
                db,
                str(task.id),
                f"Agent failed {circuit_info['failure_count']} times. "
                f"Last error: {bug_report.get('summary', 'Tests failed') if bug_report else 'Tests failed'}"
            )

            # Send escalation notification
            NotificationService.notify_task_escalation(
                str(task.id),
                task.title,
                circuit_info['reason'] or "Max retries exceeded"
            )

            return {
                "success": False,
                "error": "Task escalated due to repeated failures",
                "details": {
                    "escalated": True,
                    "failure_count": circuit_info["failure_count"],
                },
            }

        if feature.retry_count < MAX_RETRY_ATTEMPTS:
            # Attempt self-healing via Coding Agent patch
            patch_and_retry.delay(task_id, feature_id, json.dumps(bug_report or {}))
        else:
            # Max retries exceeded — escalate to human
            task.status = TaskStatus.ESCALATED
            task.escalation_reason = (
                f"Tests failed after {MAX_RETRY_ATTEMPTS} attempts. "
                f"Last error: {bug_report.get('summary', 'Unknown') if bug_report else 'Unknown'}"
            )
            log_esc = AgentLog(
                agent_type=AgentType.TESTING,
                task_id=task.id,
                action="task_escalated",
                details={
                    "reason": task.escalation_reason,
                    "retry_count": feature.retry_count,
                },
                status=AgentLogStatus.FAILURE,
                error_message=task.escalation_reason,
            )
            db.add(log_esc)
            db.commit()

            # Send escalation notification
            NotificationService.notify_task_escalation(
                str(task.id),
                task.title,
                task.escalation_reason
            )

        return {
            "success": False,
            "error": bug_report.get("summary") if bug_report else "Tests failed",
            "details": {
                "retry_count": feature.retry_count,
                "escalated": feature.retry_count >= MAX_RETRY_ATTEMPTS or should_escalate_now,
            },
        }

    except Exception as exc:
        log_err = AgentLog(
            agent_type=AgentType.TESTING,
            task_id=uuid.UUID(task_id) if task_id else None,
            action="run_tests_error",
            details={"error": str(exc)},
            status=AgentLogStatus.FAILURE,
            error_message=str(exc),
        )
        db.add(log_err)
        db.commit()
        self.retry(countdown=30, exc=exc)
    finally:
        db.close()


@celery_app.task(name="workers.tasks.patch_and_retry", bind=True, max_retries=1)
def patch_and_retry(self, task_id: str, feature_id: str, bug_report_json: str) -> dict:
    """
    Celery task: Patch tool code based on a Testing Agent bug report, then re-run tests.

    Called when run_tests fails and retry_count < MAX_RETRY_ATTEMPTS.
    """
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == uuid.UUID(task_id)).first()
        feature = db.query(Feature).filter(Feature.id == uuid.UUID(feature_id)).first()

        if not task or not feature:
            return {"success": False, "error": "Task or Feature not found", "details": {}}

        bug_report: dict = json.loads(bug_report_json) if bug_report_json else {}

        log_start = AgentLog(
            agent_type=AgentType.CODING,
            task_id=task.id,
            action="patch_code_started",
            details={
                "tool_name": feature.tool_name,
                "attempt": feature.retry_count,
                "bug_summary": bug_report.get("summary", ""),
            },
            status=AgentLogStatus.IN_PROGRESS,
        )
        db.add(log_start)
        db.commit()

        coding_agent = get_coding_agent()
        patch_result = coding_agent.patch_code(task, feature, bug_report)

        if patch_result["success"]:
            # Persist the patched code to the feature record
            feature.tool_code = patch_result.get("patched_code") or feature.tool_code
            feature.status = FeatureStatus.DEVELOPMENT

            log_ok = AgentLog(
                agent_type=AgentType.CODING,
                task_id=task.id,
                action="patch_code_success",
                details={
                    "tool_name": feature.tool_name,
                    "files_patched": patch_result.get("files_created", []),
                },
                status=AgentLogStatus.SUCCESS,
            )
            db.add(log_ok)
            db.commit()

            # Re-queue tests
            run_tests.delay(task_id, feature_id)
            return {"success": True, "error": None, "details": {}}

        # Patch itself failed — escalate immediately
        task.status = TaskStatus.ESCALATED
        task.escalation_reason = (
            f"Code patching failed: {patch_result.get('error', 'Unknown error')}"
        )
        feature.status = FeatureStatus.FAILED

        log_fail = AgentLog(
            agent_type=AgentType.CODING,
            task_id=task.id,
            action="patch_code_failed",
            details={"error": patch_result.get("error", "")},
            status=AgentLogStatus.FAILURE,
            error_message=patch_result.get("error", ""),
        )
        db.add(log_fail)
        db.commit()

        return {
            "success": False,
            "error": patch_result.get("error"),
            "details": {"escalated": True},
        }

    except Exception as exc:
        log_err = AgentLog(
            agent_type=AgentType.CODING,
            task_id=uuid.UUID(task_id) if task_id else None,
            action="patch_and_retry_error",
            details={"error": str(exc)},
            status=AgentLogStatus.FAILURE,
            error_message=str(exc),
        )
        db.add(log_err)
        db.commit()
        self.retry(countdown=30, exc=exc)
    finally:
        db.close()


# ── Phase 6 tasks ─────────────────────────────────────────────────────────────

@celery_app.task(name="workers.tasks.handle_pr_approved", bind=True, max_retries=1)
def handle_pr_approved(self, task_id: str, pr_number: int) -> dict:
    """
    Celery task: Handle PR approval via GitHub webhook.

    When a human approves a PR on GitHub, update task status to PENDING_DEPLOYMENT.
    """
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == uuid.UUID(task_id)).first()
        if not task:
            return {"success": False, "error": "Task not found"}

        task.status = TaskStatus.PENDING_DEPLOYMENT

        log_entry = AgentLog(
            agent_type=AgentType.CODING,
            task_id=task.id,
            action="pr_approved_webhook",
            details={"pr_number": pr_number},
            status=AgentLogStatus.SUCCESS,
        )
        db.add(log_entry)
        db.commit()
        return {"success": True, "error": None}

    except Exception as exc:
        log_err = AgentLog(
            agent_type=AgentType.CODING,
            task_id=uuid.UUID(task_id) if task_id else None,
            action="pr_approval_error",
            details={"error": str(exc)},
            status=AgentLogStatus.FAILURE,
            error_message=str(exc),
        )
        db.add(log_err)
        db.commit()
        self.retry(countdown=30, exc=exc)
    finally:
        db.close()


@celery_app.task(name="workers.tasks.handle_pr_merged", bind=True, max_retries=1)
def handle_pr_merged(self, task_id: str, pr_number: int) -> dict:
    """
    Celery task: Handle PR merge via GitHub webhook.

    When a PR is merged to main, update task and feature status to DEPLOYED.
    This is the final state of a successfully developed feature.
    """
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == uuid.UUID(task_id)).first()
        feature = db.query(Feature).filter(Feature.task_id == uuid.UUID(task_id)).first()

        if not task or not feature:
            return {"success": False, "error": "Task or Feature not found"}

        task.status = TaskStatus.DEPLOYED
        task.deployed_at = datetime.now(timezone.utc)
        feature.status = FeatureStatus.DEPLOYED
        feature.merged_at = datetime.now(timezone.utc)
        feature.pr_status = "merged"

        log_entry = AgentLog(
            agent_type=AgentType.CODING,
            task_id=task.id,
            action="pr_merged_webhook",
            details={
                "pr_number": pr_number,
                "tool_name": feature.tool_name,
            },
            status=AgentLogStatus.SUCCESS,
        )
        db.add(log_entry)
        db.commit()

        # ── Phase 8: Send deployment notification ────────────────
        NotificationService.notify_deployment_complete(
            str(task.id),
            task.title,
            feature.tool_name,
            f"v{datetime.now(timezone.utc).strftime('%Y%m%d.%H%M%S')}"
        )

        return {"success": True, "error": None}

    except Exception as exc:
        log_err = AgentLog(
            agent_type=AgentType.CODING,
            task_id=uuid.UUID(task_id) if task_id else None,
            action="pr_merge_error",
            details={"error": str(exc)},
            status=AgentLogStatus.FAILURE,
            error_message=str(exc),
        )
        db.add(log_err)
        db.commit()
        self.retry(countdown=30, exc=exc)
    finally:
        db.close()
