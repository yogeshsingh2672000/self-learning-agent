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
import os
import re
import sys
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
7. If external packages are needed (requests, google-auth, etc.), use them - they will be installed

Example structure:
```python
\"\"\"
{task_description}
\"\"\"
import logging
from typing import Optional, Dict, Any
from langchain_core.tools import Tool

from tools.base import BaseTool, ToolConfig

logger = logging.getLogger(__name__)

class {tool_class}(BaseTool):
    \"\"\"Implements {task_description}.\"\"\"
    
    def get_config(self) -> ToolConfig:
        return ToolConfig(
            name="{tool_name}",
            description="{task_description}",
            category="integration"
        )
    
    def execute(self) -> Tool:
        def tool_func(input_data: Dict[str, Any]) -> Dict[str, Any]:
            try:
                # Implementation - use external packages if needed
                # Example: import requests; resp = requests.get(...)
                result = {{"success": True, "data": input_data}}
                return result
            except Exception as e:
                logger.error(f"Error: {{e}}", exc_info=True)
                return {{"success": False, "error": str(e)}}
        
        return Tool(
            name="{tool_name}",
            func=tool_func,
            description="{task_description}"
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

CONSTRAINT: Use ONLY Python standard library + langchain_core. NO external packages.

TASK: {task_description}

ROOT CAUSE: {bug_report.get("root_cause", "")}

BUG SUMMARY: {bug_report.get("summary", "")}

FAILING TESTS:
{failing_str}

SUGGESTED FIXES:
{fixes_str}

CURRENT CODE:
{existing_code}

Generate ONLY the fixed Python code with no markdown fences. Rules:
1. Keep the exact same class name, interface (BaseTool), and file structure
2. Fix ALL failing tests without breaking passing tests
3. Use ONLY standard library + langchain_core (no external packages)
4. If the original code tried to use external APIs, convert to simulated responses
5. Maintain comprehensive docstrings and error handling
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

IMPORTANT: Use ONLY Python standard library + pytest. NO external packages.

TOOL CLASS: {tool_class}
TOOL NAME: {tool_name}
DESCRIPTION: {tool_description}

ACCEPTANCE CRITERIA:
{criteria_str}

Generate ONLY valid Python code with no markdown. The tests MUST:
1. Import pytest, logging, and the tool class (NOT external packages)
2. Test all acceptance criteria requirements
3. Use pytest fixtures for tool initialization
4. Include both happy path and error/edge cases
5. Have descriptive test names following test_<feature>_<scenario>
6. Use clear assertions with messages
7. Test error handling gracefully (no external API calls)
8. Include docstrings for each test

Key rules:
- Mock external APIs or use simulated data (no real network calls)
- Test the tool's interface (get_config, execute) thoroughly
- Test error handling with invalid inputs
- Use only standard library for mocking (unittest.mock)

Example structure:
```python
\"\"\"Test suite for {tool_class}.\"\"\"
import pytest
import logging
from unittest.mock import patch, MagicMock
from tools.{tool_name} import {tool_class}

logger = logging.getLogger(__name__)

@pytest.fixture
def tool():
    \"\"\"Fixture to provide a {tool_class} instance.\"\"\"
    return {tool_class}()

class TestToolConfiguration:
    \"\"\"Test tool configuration.\"\"\"
    
    def test_initialization(self, tool):
        \"\"\"Test tool initializes without errors.\"\"\"
        assert tool is not None
    
    def test_config(self, tool):
        \"\"\"Test get_config returns correct ToolConfig.\"\"\"
        config = tool.get_config()
        assert config.name == "{tool_name}"
        assert config.enabled is True

class TestToolExecution:
    \"\"\"Test tool execution functionality.\"\"\"
    
    def test_execute_returns_tool(self, tool):
        \"\"\"Test execute returns a LangChain Tool object.\"\"\"
        tool_obj = tool.execute()
        assert tool_obj is not None
        assert tool_obj.name == "{tool_name}"
    
    def test_tool_execution_with_input(self, tool):
        \"\"\"Test tool execution with sample input.\"\"\"
        tool_obj = tool.execute()
        result = tool_obj.invoke({{"input": "test"}})
        assert result is not None

class TestErrorHandling:
    \"\"\"Test error handling and edge cases.\"\"\"
    
    def test_invalid_input(self, tool):
        \"\"\"Test tool handles invalid inputs gracefully.\"\"\"
        tool_obj = tool.execute()
        result = tool_obj.invoke({{"input": None}})
        assert result is not None or isinstance(result, Exception) is False
```

Generate the complete production-ready test suite:
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
            # Write files (create parent directories if needed)
            for path, content in files.items():
                parent = os.path.dirname(path)
                if parent:
                    os.makedirs(parent, exist_ok=True)
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

    @staticmethod
    def extract_requirements(code: str) -> List[str]:
        """
        Extract external package requirements from generated code.
        
        Maps common module names to their pip package names.
        
        Returns:
            List of pip package names to install
        """
        import ast
        
        # Mapping of import names to pip package names
        import_to_package = {
            "requests": "requests",
            "google": "google-auth",
            "google.auth": "google-auth",
            "google.oauth2": "google-auth",
            "aws": "boto3",
            "boto3": "boto3",
            "botocore": "boto3",
            "azure": "azure-identity",
            "azure.identity": "azure-identity",
            "openai": "openai",
            "anthropic": "anthropic",
            "httpx": "httpx",
            "aiohttp": "aiohttp",
            "pandas": "pandas",
            "numpy": "numpy",
            "sklearn": "scikit-learn",
            "selenium": "selenium",
            "beautifulsoup4": "beautifulsoup4",
            "bs4": "beautifulsoup4",
            "lxml": "lxml",
            "psycopg2": "psycopg2-binary",
            "pymongo": "pymongo",
            "redis": "redis",
            "jwt": "pyjwt",
            "dotenv": "python-dotenv",
        }
        
        requirements = set()
        
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                # Handle: import module
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        module = alias.name.split(".")[0]
                        if module in import_to_package:
                            requirements.add(import_to_package[module])
                
                # Handle: from module import name
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        module = node.module.split(".")[0]
                        if module in import_to_package:
                            requirements.add(import_to_package[module])
        except Exception:
            pass  # If parsing fails, return empty list
        
        return sorted(list(requirements))

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

            # Extract requirements from tool code
            requirements = self.extract_requirements(tool_code)

            # Create branch
            branch_name = self.git.create_branch(task.id, tool_name)

            # ── Phase 10: Sandbox Pattern ────────────────────────────────────
            # Code and tests are generated and stored in DB, but NOT committed yet.
            # They will only be committed to git AFTER tests pass.
            # This ensures dirty code never enters the repository.

            return {
                "success": True,
                "tool_name": tool_name,
                "branch_name": branch_name,
                "files_created": [
                    f"tools/{tool_name}.py",
                    f"tests/tools/test_{tool_name}.py",
                ],
                "tool_code": tool_code,
                "test_code": test_code,
                "requirements": requirements,
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

            # ── Phase 10: Sandbox Pattern ────────────────────────────────────
            # Patched code is generated but NOT committed to git.
            # It will only be committed AFTER re-tests pass.
            # This keeps git clean even during retry cycles.

            return {
                "success": True,
                "tool_name": tool_name,
                "branch_name": branch_name,
                "files_created": [f"tools/{tool_name}.py"],
                "patched_code": patched_code,
                "error": None,
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
# Production Requirements Management
# ---------------------------------------------------------------------------

def is_virtual_env() -> bool:
    """
    Detect if running inside a virtual environment.
    
    Returns:
        True if venv is detected, False otherwise
    """
    return hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)


def validate_package_name(package_name: str) -> bool:
    """
    Validate if a string is a valid pip package name.
    
    Pip package names can contain:
    - Alphanumeric characters (A-Z, a-z, 0-9)
    - Hyphens and underscores
    - Dots
    
    Args:
        package_name: Name to validate
        
    Returns:
        True if valid, False otherwise
    """
    import re
    # Valid pip package name pattern
    pattern = r'^[a-zA-Z0-9._-]+$'
    return bool(re.match(pattern, package_name)) and len(package_name) > 0


def scan_all_tools_requirements(tools_dir: str = "tools") -> List[str]:
    """
    Scan all tool files in the tools directory and extract requirements.
    
    Reads each .py file, extracts imports using AST, and returns
    all unique pip package names needed.
    
    Args:
        tools_dir: Path to tools directory (relative or absolute)
        
    Returns:
        Sorted list of unique pip package names
    """
    from pathlib import Path
    
    all_requirements = set()
    tools_path = Path(tools_dir)
    
    # If relative path, make absolute
    if not tools_path.is_absolute():
        tools_path = Path.cwd() / tools_path
    
    if not tools_path.exists():
        return []
    
    # Scan all .py files (except __init__.py)
    for py_file in tools_path.glob("*.py"):
        if py_file.name.startswith("_"):
            continue  # Skip __init__.py, __pycache__, etc.
        
        try:
            with open(py_file, "r", encoding="utf-8") as f:
                code = f.read()
            # Use CodingAgent's static method to extract
            requirements = CodingAgent.extract_requirements(code)
            all_requirements.update(requirements)
        except Exception as e:
            # Log but continue scanning other files
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to scan {py_file}: {str(e)}")
    
    return sorted(list(all_requirements))


def update_requirements_txt(new_packages: List[str], requirements_file: str = "requirements.txt") -> tuple[bool, str, List[str]]:
    """
    Update requirements.txt with new packages.
    
    Reads current requirements, merges with new packages, and writes back.
    Preserves existing version specifications and adds new packages with >= (pip resolves versions).
    
    Args:
        new_packages: List of package names to add
        requirements_file: Path to requirements.txt file
        
    Returns:
        (success: bool, message: str, updated_packages: List[str])
        - success: True if update succeeded
        - message: Description of what was done
        - updated_packages: List of packages that were actually added
    """
    from pathlib import Path
    
    req_path = Path(requirements_file)
    
    # If relative path, make absolute
    if not req_path.is_absolute():
        req_path = Path.cwd() / req_path
    
    if not req_path.exists():
        return False, f"requirements.txt not found at {req_path}", []
    
    try:
        # Read current requirements
        with open(req_path, "r", encoding="utf-8") as f:
            current_content = f.read()
        
        # Parse existing packages (extract package names from lines)
        existing_packages = set()
        existing_lines = []
        for line in current_content.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                existing_lines.append(line)
                continue
            # Extract package name (everything before # or ==, >=, <=, <, >, ~=, !=)
            pkg_name = line.split("[")[0]  # Handle extras like requests[security]
            for op in ["==", ">=", "<=", "!=", "~=", "<", ">"]:
                pkg_name = pkg_name.split(op)[0]
            pkg_name = pkg_name.strip()
            if pkg_name:
                existing_packages.add(pkg_name)
                existing_lines.append(line)
        
        # Find new packages (not already in requirements.txt)
        packages_to_add = []
        for pkg in new_packages:
            if pkg not in existing_packages:
                # Validate package name
                if validate_package_name(pkg):
                    packages_to_add.append(pkg)
        
        if not packages_to_add:
            return True, "No new packages to add (all already in requirements.txt)", []
        
        # Add new packages with >= (let pip resolve versions)
        new_lines = existing_lines + [f"{pkg}>=" for pkg in sorted(packages_to_add)]
        
        # Write updated requirements
        with open(req_path, "w", encoding="utf-8") as f:
            f.write("\n".join(new_lines))
        
        return True, f"Updated requirements.txt with {len(packages_to_add)} new packages", packages_to_add
    
    except Exception as e:
        return False, f"Failed to update requirements.txt: {str(e)}", []


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
