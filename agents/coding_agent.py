"""
Coding Agent — Phase 4 + Phase 6

Responsibilities:
1. Generate tool code from approved tasks (following BaseTool interface)
2. Generate unit tests
3. Create feature branch on GitHub
4. Commit and push code
5. Update task status to in_development
6. Create GitHub PR after tests pass (Phase 6)
7. Log execution steps

This agent is triggered via Celery worker when a task transitions to APPROVED status.
"""
import re
import json
import uuid
import subprocess
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from github import Github, GithubException

from core.config import settings
from core.database import get_db
from core.models import Task, TaskStatus, Feature, FeatureStatus, AgentLog, AgentType, AgentLogStatus


# ---------------------------------------------------------------------------
# Code generators
# ---------------------------------------------------------------------------

class ToolCodeGenerator:
    """Generates Python tool code following BaseTool interface."""

    def __init__(self, llm: ChatOpenAI):
        self.llm = llm

    def generate_tool_code(
        self,
        task_title: str,
        task_description: str,
        acceptance_criteria: List[str],
    ) -> str:
        """
        Generate a complete tool implementation.

        Args:
            task_title: The name/title of the tool
            task_description: What the tool does
            acceptance_criteria: List of requirements

        Returns:
            Python code as string (ready to write to file)
        """
        # Sanitize tool name
        tool_name = re.sub(r"[^a-z0-9_]", "_", task_title.lower())
        tool_class = "".join(word.capitalize() for word in tool_name.split("_"))

        criteria_str = "\n".join(f"   - {c}" for c in acceptance_criteria)

        prompt = f"""Generate a complete Python tool that implements the BaseTool interface.

TOOL NAME: {tool_name}
DESCRIPTION: {task_description}

REQUIREMENTS (acceptance criteria):
{criteria_str}

Generate ONLY valid Python code with no markdown. The tool MUST:
1. Import from tools.base import BaseTool, ToolConfig
2. Implement a class named {tool_class} inheriting from BaseTool
3. Implement get_config() returning ToolConfig with name="{tool_name}"
4. Implement execute() returning a LangChain Tool object
5. Include comprehensive docstrings
6. Handle errors gracefully

Example structure:
```python
from tools.base import BaseTool, ToolConfig
from langchain_core.tools import Tool
from typing import Optional

class {tool_class}(BaseTool):
    def get_config(self) -> ToolConfig:
        return ToolConfig(
            name="{tool_name}",
            description="...",
            category="category"
        )
    
    def execute(self) -> Tool:
        def tool_func(input_param: str) -> str:
            # Implementation
            return "result"
        
        return Tool(
            name="{tool_name}",
            func=tool_func,
            description="..."
        )
```

Generate the complete implementation now:
"""

        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            code = response.content.strip()
            # Remove markdown code blocks if present
            if code.startswith("```"):
                code = code.split("```")[1]
                if code.startswith("python"):
                    code = code[6:]
                code = code.rstrip("`").strip()
            return code
        except Exception as e:
            raise ValueError(f"Failed to generate tool code: {str(e)}")

    def generate_patch(
        self,
        existing_code: str,
        bug_report: Dict[str, Any],
        task_description: str,
    ) -> str:
        """
        Re-generate tool code fixed based on a bug report from the Testing Agent.

        Args:
            existing_code:    The current (failing) tool implementation
            bug_report:       Structured report from BugReportGenerator
            task_description: Original task description for context

        Returns:
            Patched Python source (no markdown fences)
        """
        failing_str = "\n".join(
            f"  - {t.get('name', '')}: {t.get('message', '')[:300]}"
            for t in bug_report.get("failing_tests", [])
        )
        fixes_str = "\n".join(
            f"  {i+1}. {fix}"
            for i, fix in enumerate(bug_report.get("suggested_fixes", []))
        )

        prompt = f"""You are a senior Python engineer fixing a generated tool.

TASK: {task_description}

ROOT CAUSE: {bug_report.get("root_cause", "")}

BUG SUMMARY: {bug_report.get("summary", "")}

FAILING TESTS:
{failing_str}

SUGGESTED FIXES:
{fixes_str}

CURRENT CODE:
{existing_code}

Generate ONLY the fixed Python code with no markdown fences.
Keep the exact same class name, interface (BaseTool), and file structure.
Fix all failing tests without breaking tests that were passing.
"""
        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            code = response.content.strip()
            if code.startswith("```"):
                code = code.split("```")[1]
                if code.startswith("python"):
                    code = code[6:]
                code = code.rstrip("`").strip()
            return code
        except Exception as exc:
            raise ValueError(f"Failed to generate patch: {str(exc)}")


class TestCodeGenerator:
    """Generates unit tests for tools."""

    def __init__(self, llm: ChatOpenAI):
        self.llm = llm

    def generate_test_code(
        self,
        tool_name: str,
        tool_class: str,
        tool_description: str,
        acceptance_criteria: List[str],
    ) -> str:
        """Generate pytest-compatible test code."""
        criteria_str = "\n".join(f"   - {c}" for c in acceptance_criteria)

        prompt = f"""Generate comprehensive pytest test cases for a tool.

TOOL CLASS: {tool_class}
TOOL NAME: {tool_name}
DESCRIPTION: {tool_description}

ACCEPTANCE CRITERIA:
{criteria_str}

Generate ONLY valid Python code with no markdown. The tests MUST:
1. Import pytest and the tool class
2. Test all requirements from acceptance criteria
3. Use fixtures for tool initialization
4. Include both happy path and error cases
5. Have descriptive test names
6. Include docstrings

Example structure:
```python
import pytest
from tools.{tool_name} import {tool_class}

@pytest.fixture
def tool():
    return {tool_class}()

def test_tool_config(tool):
    config = tool.get_config()
    assert config.name == "{tool_name}"
    assert config.enabled is True

def test_tool_execute(tool):
    tool_obj = tool.execute()
    assert tool_obj is not None
    assert tool_obj.name == "{tool_name}"
```

Generate the complete test suite now:
"""

        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            code = response.content.strip()
            if code.startswith("```"):
                code = code.split("```")[1]
                if code.startswith("python"):
                    code = code[6:]
                code = code.rstrip("`").strip()
            return code
        except Exception as e:
            raise ValueError(f"Failed to generate test code: {str(e)}")


# ---------------------------------------------------------------------------
# Git operations
# ---------------------------------------------------------------------------

class GitOperations:
    """Handle git branch creation, commits, and pushes."""

    @staticmethod
    def create_branch(task_id: str, tool_name: str) -> str:
        """
        Create a feature branch locally.

        Returns:
            Branch name (e.g., "feature/agent/abc123-tool_name")
        """
        short_id = str(task_id)[:8]
        branch = f"feature/agent/{short_id}-{tool_name}"
        try:
            subprocess.run(["git", "checkout", "-b", branch], check=True, cwd=".")
            return branch
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to create branch {branch}: {str(e)}")

    @staticmethod
    def commit_code(branch: str, files: Dict[str, str], message: str) -> bool:
        """
        Stage files, commit, and push.

        Args:
            branch: Branch name
            files: {"path": "content"} dict
            message: Commit message

        Returns:
            True if successful
        """
        try:
            # Write files
            for path, content in files.items():
                with open(path, "w") as f:
                    f.write(content)

            # Stage and commit
            subprocess.run(["git", "add", "-A"], check=True, cwd=".")
            subprocess.run(["git", "commit", "-m", message], check=True, cwd=".")

            # Push
            subprocess.run(["git", "push", "-u", "origin", branch], check=True, cwd=".")

            return True
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to commit/push: {str(e)}")


# ---------------------------------------------------------------------------
# CodingAgent
# ---------------------------------------------------------------------------

class CodingAgent:
    """
    Orchestrates code generation and git operations.

    Called when a task is approved, generates tool code + tests,
    creates feature branch, commits, pushes, and updates task status.
    """

    def __init__(self, llm_provider: str = "openai", temperature: float = 0.3):
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY not set in .env")
        self.llm = ChatOpenAI(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            temperature=temperature,
        )
        self.code_gen = ToolCodeGenerator(self.llm)
        self.test_gen = TestCodeGenerator(self.llm)
        self.git = GitOperations()

    def _sanitize_name(self, name: str) -> str:
        """Convert title to valid Python name."""
        return re.sub(r"[^a-z0-9_]", "_", name.lower())

    def _get_class_name(self, tool_name: str) -> str:
        """Convert tool_name to CamelCase class name."""
        return "".join(word.capitalize() for word in tool_name.split("_"))

    def generate_code(
        self,
        task: Task,
    ) -> Dict[str, Any]:
        """
        Full pipeline: generate code, tests, create branch, commit, push.

        Returns:
            {
                "success": bool,
                "tool_name": str,
                "branch_name": str,
                "files_created": [str],
                "error": str | None,
            }
        """
        try:
            # Parse acceptance criteria
            criteria = task.acceptance_criteria
            if isinstance(criteria, str):
                try:
                    criteria = json.loads(criteria)
                except Exception:
                    criteria = [criteria] if criteria else []

            tool_name = self._sanitize_name(task.title)
            tool_class = self._get_class_name(tool_name)

            # Generate code
            tool_code = self.code_gen.generate_tool_code(
                task.title, task.description, criteria or []
            )

            test_code = self.test_gen.generate_test_code(
                tool_name, tool_class, task.description, criteria or []
            )

            # Create branch
            branch_name = self.git.create_branch(task.id, tool_name)

            # Prepare files
            files = {
                f"tools/{tool_name}.py": tool_code,
                f"tests/tools/test_{tool_name}.py": test_code,
            }

            # Commit and push
            self.git.commit_code(
                branch_name,
                files,
                f"feat: implement {tool_name} tool\n\nCloses task {task.id}",
            )

            return {
                "success": True,
                "tool_name": tool_name,
                "branch_name": branch_name,
                "files_created": list(files.keys()),
                "error": None,
            }

        except Exception as e:
            return {
                "success": False,
                "tool_name": None,
                "branch_name": None,
                "files_created": [],
                "error": str(e),
            }

    def patch_code(
        self,
        task: "Task",  # type: ignore[name-defined]
        feature: "Feature",  # type: ignore[name-defined]
        bug_report: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Patch existing tool code based on a Testing Agent bug report.

        Called by the Celery `patch_and_retry` task when tests fail.
        Checks out the existing feature branch, regenerates the tool code
        with fixes applied, commits, and pushes.

        Returns:
          {
            "success":      bool,
            "tool_name":    str | None,
            "branch_name":  str | None,
            "files_created": [str],
            "error":        str | None,
          }
        """
        try:
            if not feature.tool_code:
                raise ValueError("Feature has no tool_code to patch")

            tool_name = feature.tool_name or self._sanitize_name(task.title)
            branch_name = feature.branch_name

            # Checkout the feature branch before making changes
            subprocess.run(
                ["git", "checkout", branch_name],
                check=True,
                cwd=".",
                capture_output=True,
            )

            # Generate patched code
            patched_code = self.code_gen.generate_patch(
                existing_code=feature.tool_code,
                bug_report=bug_report,
                task_description=task.description,
            )

            attempt = (feature.retry_count or 0) + 1
            files = {f"tools/{tool_name}.py": patched_code}

            self.git.commit_code(
                branch_name,
                files,
                f"fix: patch {tool_name} (attempt {attempt})\n\nAddresses test failures from Testing Agent\nTask: {task.id}",
            )

            return {
                "success": True,
                "tool_name": tool_name,
                "branch_name": branch_name,
                "files_created": list(files.keys()),
                "error": None,
                "patched_code": patched_code,
            }

        except Exception as exc:
            return {
                "success": False,
                "tool_name": None,
                "branch_name": None,
                "files_created": [],
                "error": str(exc),
                "patched_code": None,
            }

    def create_pr(
        self,
        task: "Task",  # type: ignore[name-defined]
        feature: "Feature",  # type: ignore[name-defined]
    ) -> Dict[str, Any]:
        """
        Create a GitHub PR for a feature branch after tests pass.

        Triggered after successful testing (Phase 5). Creates PR with:
        - Title: task title
        - Body: auto-generated summary (what it does, test coverage, links to task)
        - Labels: agent-generated, needs-review
        - Base branch: main

        Returns:
          {
            "success":    bool,
            "pr_url":     str | None,
            "pr_number":  int | None,
            "error":      str | None,
          }
        """
        if not settings.github_token or not settings.github_repo:
            return {
                "success": False,
                "pr_url": None,
                "pr_number": None,
                "error": "GitHub token or repo not configured",
            }

        try:
            gh = Github(settings.github_token)
            repo = gh.get_repo(settings.github_repo)

            test_results = feature.test_results or {}
            coverage_pct = test_results.get("coverage_percent", 0.0)
            passed_count = test_results.get("passed_count", 0)
            total_count = test_results.get("total", 0)

            # Build PR body
            pr_body = f"""# {task.title}

## Description
{task.description}

## Test Results
- ✅ Passed: {passed_count}/{total_count}
- 📊 Coverage: {coverage_pct}%

## Linked Task
[Task #{str(task.id)[:8]}](./tasks/{task.id})

**Branch**: {feature.branch_name}

---
*This PR was automatically generated by the Self-Improving Agent Platform (Phase 6).*
"""

            # Create PR
            pr = repo.create_pull(
                title=task.title,
                body=pr_body,
                head=feature.branch_name,
                base="main",
            )

            # Add labels
            try:
                pr.add_to_labels("agent-generated", "needs-review")
            except Exception:
                # Labels might not exist; ignore
                pass

            return {
                "success": True,
                "pr_url": pr.html_url,
                "pr_number": pr.number,
                "error": None,
            }

        except GithubException as exc:
            return {
                "success": False,
                "pr_url": None,
                "pr_number": None,
                "error": f"GitHub API error: {str(exc)}",
            }
        except Exception as exc:
            return {
                "success": False,
                "pr_url": None,
                "pr_number": None,
                "error": str(exc),
            }


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_instance: Optional[CodingAgent] = None


def get_coding_agent() -> CodingAgent:
    """Return a singleton CodingAgent (lazy init)."""
    global _instance
    if _instance is None:
        _instance = CodingAgent()
    return _instance
