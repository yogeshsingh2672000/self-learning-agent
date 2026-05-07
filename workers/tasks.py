"""
Background task definitions.

Phase 4: generate_tool_code — triggered when a task is APPROVED
Phase 5: run_tests           — triggered when code generation succeeds
         patch_and_retry     — triggered when tests fail (≤3 attempts)
Phase 6: handle_pr_approved, handle_pr_merged — GitHub webhook handlers
Phase 8: Rate limiting, cost controls, circuit breaker, notifications
Phase 9: Auto-update requirements.txt with generated tool packages
"""
import json
import uuid
import os
import subprocess
import logging
from datetime import datetime, timezone

from workers.celery_app import celery_app
from core.database import SessionLocal
from core.models import Task, TaskStatus, Feature, FeatureStatus, AgentLog, AgentType, AgentLogStatus
from core.hardening import RateLimiter, CostController, CircuitBreaker
from core.notifications import NotificationService
from core.config import settings
from agents.coding_agent import get_coding_agent, CodingAgent, is_virtual_env, scan_all_tools_requirements, update_requirements_txt

logger = logging.getLogger(__name__)


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
            # ── Phase 10: Sandbox Pattern ────────────────────────────────────
            # Code is generated and stored in Feature record, but NOT committed yet.
            # It will be committed to git ONLY AFTER tests pass in run_tests task.
            
            # Create Feature record with generated code and requirements
            feature = Feature(
                task_id=task.id,
                branch_name=result["branch_name"],
                tool_name=result["tool_name"],
                tool_code=result.get("tool_code", ""),
                test_code=result.get("test_code", ""),
                requirements=result.get("requirements", []),
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
                    "requirements": result.get("requirements", []),
                    "status": "code generated, awaiting test in sandbox",
                },
                status=AgentLogStatus.SUCCESS,
            )
            db.add(log_entry)
            db.commit()

            # Refresh to get the new feature ID, then trigger Phase 5 testing
            db.refresh(feature)
            run_tests.delay(str(task.id), str(feature.id), json.dumps(result.get("requirements", [])))

            return {
                "success": True,
                "error": None,
                "details": {
                    "tool_name": result["tool_name"],
                    "branch_name": result["branch_name"],
                    "files_created": result["files_created"],
                    "requirements": result.get("requirements", []),
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
def run_tests(self, task_id: str, feature_id: str, requirements_json: str = "[]") -> dict:
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

        # Parse requirements
        try:
            requirements = json.loads(requirements_json) if requirements_json else []
        except Exception:
            requirements = feature.requirements or []

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
                "requirements": requirements,
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
            requirements=requirements,
        )

        test_results = result["test_results"]
        bug_report = result.get("bug_report")

        # Persist test results (include bug_report inside the JSON)
        combined_results = dict(test_results)
        if bug_report:
            combined_results["bug_report"] = bug_report

        feature.test_results = combined_results

        if result["passed"]:
            # ── Tests passed — commit code and create PR ────────────────────
            # Phase 10 (Sandbox Pattern): Tests passed, so now it's safe to commit
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

            # Trigger commit_tool_code task which will:
            # 1. Write code to disk
            # 2. Commit to git
            # 3. Create PR
            commit_tool_code.delay(str(task.id), str(feature.id))

            db.commit()
            return {"success": True, "error": None, "details": {"status": "committing_and_creating_pr"}}


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
            patch_and_retry.delay(
                task_id, feature_id, json.dumps(bug_report or {}), 
                json.dumps(feature.requirements or [])
            )
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

# ---------------------------------------------------------------------------
# Phase 10: Commit Tool Code (Sandbox Pattern)
# ---------------------------------------------------------------------------

@celery_app.task(name="workers.tasks.commit_tool_code", bind=True, max_retries=1)
def commit_tool_code(self, task_id: str, feature_id: str) -> dict:
    """
    Celery task: Write tool code to disk and commit to git.
    
    Phase 10 (Sandbox Pattern): Only called AFTER tests pass.
    
    This ensures code is NEVER committed unless it passes tests.
    - Tests pass → commit to git and create PR
    - Tests fail → patch and re-test (no commits made)
    - All retries fail → escalate (no commits made)
    
    This keeps the git repository clean and prevents dirty code from being committed.
    """
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == uuid.UUID(task_id)).first()
        feature = db.query(Feature).filter(Feature.id == uuid.UUID(feature_id)).first()

        if not task or not feature:
            return {"success": False, "error": "Task or Feature not found"}

        if not feature.tool_code or not feature.test_code:
            return {"success": False, "error": "Feature missing tool_code or test_code"}

        tool_name = feature.tool_name
        branch_name = feature.branch_name

        log_entry = AgentLog(
            agent_type=AgentType.CODING,
            task_id=task.id,
            action="commit_tool_code_started",
            details={
                "tool_name": tool_name,
                "branch_name": branch_name,
            },
            status=AgentLogStatus.IN_PROGRESS,
        )
        db.add(log_entry)
        db.commit()

        # ── Phase 10: NOW write to disk and commit ──────────────────────────
        # This only happens after tests pass, ensuring code quality.
        
        files = {
            f"tools/{tool_name}.py": feature.tool_code,
            f"tests/tools/test_{tool_name}.py": feature.test_code,
        }

        try:
            coding_agent = get_coding_agent()
            coding_agent.git.commit_code(
                branch_name,
                files,
                f"feat: implement {tool_name} tool\n\nCloses task {task.id}",
            )
        except RuntimeError as e:
            log_error = AgentLog(
                agent_type=AgentType.CODING,
                task_id=task.id,
                action="commit_tool_code_failed",
                details={"error": str(e)},
                status=AgentLogStatus.FAILURE,
                error_message=str(e),
            )
            db.add(log_error)
            db.commit()
            self.retry(countdown=30, exc=e)
            return {"success": False, "error": str(e)}

        log_success = AgentLog(
            agent_type=AgentType.CODING,
            task_id=task.id,
            action="commit_tool_code_success",
            details={
                "tool_name": tool_name,
                "branch_name": branch_name,
                "files_committed": list(files.keys()),
            },
            status=AgentLogStatus.SUCCESS,
        )
        db.add(log_success)
        db.commit()

        # ── Create PR (Phase 6) ────────────────────────────────────────
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

        return {"success": True, "error": None}

    except Exception as exc:
        log_err = AgentLog(
            agent_type=AgentType.CODING,
            task_id=uuid.UUID(task_id) if task_id else None,
            action="commit_tool_code_error",
            details={"error": str(exc)},
            status=AgentLogStatus.FAILURE,
            error_message=str(exc),
        )
        db.add(log_err)
        db.commit()
        self.retry(countdown=30, exc=exc)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Phase 5: Run Tests
# ---------------------------------------------------------------------------
@celery_app.task(name="workers.tasks.patch_and_retry", bind=True, max_retries=1)
def patch_and_retry(self, task_id: str, feature_id: str, bug_report_json: str, requirements_json: str = "[]") -> dict:
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
        
        # Parse requirements
        try:
            requirements = json.loads(requirements_json) if requirements_json else []
        except Exception:
            requirements = feature.requirements or []

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
            patched_code = patch_result.get("patched_code") or feature.tool_code
            feature.tool_code = patched_code
            feature.status = FeatureStatus.DEVELOPMENT
            
            # ── Phase 2: Re-extract requirements from patched code ────
            # The patched code might have different imports than original
            new_requirements = CodingAgent.extract_requirements(patched_code)
            old_requirements = feature.requirements or []
            
            # Update if requirements changed
            if set(new_requirements) != set(old_requirements):
                feature.requirements = new_requirements
                log_req_change = AgentLog(
                    agent_type=AgentType.CODING,
                    task_id=task.id,
                    action="patch_requirements_changed",
                    details={
                        "old_requirements": old_requirements,
                        "new_requirements": new_requirements,
                        "attempt": feature.retry_count,
                    },
                    status=AgentLogStatus.SUCCESS,
                )
                db.add(log_req_change)
                logger.info(f"Requirements changed after patch: {old_requirements} → {new_requirements}")
            else:
                log_req_same = AgentLog(
                    agent_type=AgentType.CODING,
                    task_id=task.id,
                    action="patch_requirements_unchanged",
                    details={
                        "requirements": new_requirements,
                        "attempt": feature.retry_count,
                    },
                    status=AgentLogStatus.SUCCESS,
                )
                db.add(log_req_same)

            log_ok = AgentLog(
                agent_type=AgentType.CODING,
                task_id=task.id,
                action="patch_code_success",
                details={
                    "tool_name": feature.tool_name,
                    "files_patched": patch_result.get("files_created", []),
                    "requirements": new_requirements,
                },
                status=AgentLogStatus.SUCCESS,
            )
            db.add(log_ok)
            db.commit()

            # Re-queue tests with updated requirements
            run_tests.delay(task_id, feature_id, json.dumps(new_requirements))
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
    Also scans all tools and auto-updates requirements.txt if in virtual environment.
    
    Phase 9: Auto-update production requirements with generated tool packages
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

        # ── Phase 9: Auto-update requirements.txt ────────────────────
        try:
            in_venv = is_virtual_env()
            logger.info(f"Virtual environment detected: {in_venv}")
            
            # Scan all tools for requirements
            all_requirements = scan_all_tools_requirements("tools")
            logger.info(f"Scanned tools directory, found requirements: {all_requirements}")
            
            if not all_requirements:
                log_entry_req = AgentLog(
                    agent_type=AgentType.CODING,
                    task_id=task.id,
                    action="requirements_scan_complete",
                    details={
                        "packages_found": 0,
                        "venv_detected": in_venv,
                    },
                    status=AgentLogStatus.SUCCESS,
                )
                db.add(log_entry_req)
                db.commit()
            elif in_venv:
                # Auto-update requirements.txt (venv is active - safe to auto-update)
                success, message, updated_packages = update_requirements_txt(all_requirements, "requirements.txt")
                
                log_entry_req = AgentLog(
                    agent_type=AgentType.CODING,
                    task_id=task.id,
                    action="requirements_auto_updated" if success else "requirements_update_failed",
                    details={
                        "packages_found": len(all_requirements),
                        "packages_updated": len(updated_packages),
                        "packages": updated_packages,
                        "venv_detected": in_venv,
                        "message": message,
                    },
                    status=AgentLogStatus.SUCCESS if success else AgentLogStatus.FAILURE,
                    error_message=None if success else message,
                )
                db.add(log_entry_req)
                db.commit()
                
                if success and updated_packages:
                    # Commit and push updated requirements.txt
                    try:
                        subprocess.run(
                            ["git", "add", "requirements.txt"],
                            check=True,
                            cwd=".",
                            capture_output=True,
                        )
                        subprocess.run(
                            ["git", "commit", "-m", f"chore: update requirements with {len(updated_packages)} new packages\n\nAdded: {', '.join(updated_packages)}"],
                            check=True,
                            cwd=".",
                            capture_output=True,
                        )
                        subprocess.run(
                            ["git", "push", "origin", "main"],
                            check=True,
                            cwd=".",
                            capture_output=True,
                        )
                        
                        log_commit = AgentLog(
                            agent_type=AgentType.CODING,
                            task_id=task.id,
                            action="requirements_committed",
                            details={
                                "packages_committed": updated_packages,
                                "commit_message": f"chore: update requirements with {len(updated_packages)} new packages",
                            },
                            status=AgentLogStatus.SUCCESS,
                        )
                        db.add(log_commit)
                        db.commit()
                        
                        logger.info(f"Successfully committed updated requirements.txt with {len(updated_packages)} packages")
                    except subprocess.CalledProcessError as e:
                        logger.error(f"Failed to commit requirements.txt: {str(e)}")
                        log_commit_err = AgentLog(
                            agent_type=AgentType.CODING,
                            task_id=task.id,
                            action="requirements_commit_failed",
                            details={"error": str(e)},
                            status=AgentLogStatus.FAILURE,
                            error_message=str(e),
                        )
                        db.add(log_commit_err)
                        db.commit()
            else:
                # Not in venv - require manual review
                log_entry_req = AgentLog(
                    agent_type=AgentType.CODING,
                    task_id=task.id,
                    action="requirements_manual_review_needed",
                    details={
                        "packages_found": len(all_requirements),
                        "packages": all_requirements,
                        "venv_detected": in_venv,
                        "message": "Virtual environment not detected. Manual review required before updating requirements.txt",
                    },
                    status=AgentLogStatus.IN_PROGRESS,  # Pending human action
                )
                db.add(log_entry_req)
                db.commit()
                
                logger.warning(f"Virtual environment not detected. Manual review needed. Packages: {all_requirements}")
        
        except Exception as e:
            logger.error(f"Error during requirements update: {str(e)}")
            log_req_err = AgentLog(
                agent_type=AgentType.CODING,
                task_id=task.id,
                action="requirements_scan_error",
                details={"error": str(e)},
                status=AgentLogStatus.FAILURE,
                error_message=str(e),
            )
            db.add(log_req_err)
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
