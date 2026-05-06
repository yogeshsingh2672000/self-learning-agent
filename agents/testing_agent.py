"""
Testing Agent — Phase 5

Responsibilities:
1. Generate additional LLM-driven test cases beyond what the Coding Agent wrote
2. Run the tool code + tests inside an isolated Docker sandbox (or subprocess fallback)
3. Measure pytest coverage
4. If PASS → return structured test results (triggers PR creation in Phase 6)
5. If FAIL → generate structured bug report for the Coding Agent to patch

Self-healing loop (max 3 attempts) is orchestrated by the Celery worker layer
(workers/tasks.py), not by this agent directly.

Classes:
  TestCaseGenerator  — LLM generates extra test scenarios
  SandboxRunner      — runs sandbox/run_tests.py via Docker (falls back to subprocess)
  BugReportGenerator — LLM produces a structured fix plan from test failures
  TestingAgent       — top-level orchestrator

Factory:
  get_testing_agent() → singleton TestingAgent
"""
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from core.config import settings

# Absolute path to the sandbox directory (backend/sandbox/)
_SANDBOX_DIR = Path(__file__).parent.parent / "sandbox"
_DOCKER_IMAGE = "agent-sandbox:latest"


# ---------------------------------------------------------------------------
# TestCaseGenerator
# ---------------------------------------------------------------------------

class TestCaseGenerator:
    """Uses an LLM to create additional edge-case tests for a generated tool."""

    def __init__(self, llm: ChatOpenAI) -> None:
        self.llm = llm

    def generate_additional_tests(
        self,
        tool_name: str,
        tool_class: str,
        tool_description: str,
        acceptance_criteria: List[str],
        existing_test_code: str,
    ) -> str:
        """
        Generate extra test cases not covered by the original test suite.

        Returns Python source (pytest tests) ready to append to the test file.
        Returns an empty string if generation fails (non-fatal).
        """
        criteria_str = "\n".join(f"  - {c}" for c in acceptance_criteria)

        prompt = f"""You are a QA engineer reviewing an auto-generated tool.

TOOL CLASS: {tool_class}
TOOL NAME:  {tool_name}
DESCRIPTION: {tool_description}

ACCEPTANCE CRITERIA:
{criteria_str}

EXISTING TESTS (already written — do NOT duplicate them):
{existing_test_code[:2000]}

Write additional pytest test cases covering:
1. Edge cases not handled by the existing tests (empty input, None, boundary values)
2. Error handling (invalid inputs, exceptions)
3. Integration with the BaseTool interface (get_config returns correct fields)

Rules:
- Output ONLY valid Python code — no markdown, no explanations
- Do NOT re-import or re-define fixtures that are already in the existing tests
- Each test function must have a unique name starting with `test_additional_`
- Keep it under 30 lines total
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
        except Exception:
            # Additional tests are best-effort; don't block the pipeline
            return ""


# ---------------------------------------------------------------------------
# SandboxRunner
# ---------------------------------------------------------------------------

class SandboxRunner:
    """
    Runs tool code + test code in isolation.

    Priority:
    1. Docker container (--network none, --memory 512m, --cpus 1.0)
    2. Direct subprocess fallback (when Docker is unavailable — e.g., dev env)
    """

    def _docker_available(self) -> bool:
        result = subprocess.run(
            ["docker", "version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0

    def _build_docker_image(self) -> bool:
        """Build the sandbox Docker image. Returns True on success."""
        result = subprocess.run(
            ["docker", "build", "-t", _DOCKER_IMAGE, "."],
            cwd=str(_SANDBOX_DIR),
            capture_output=True,
            text=True,
            timeout=120,
        )
        return result.returncode == 0

    def _run_in_docker(self, config_json: str) -> Dict[str, Any]:
        """Run test suite inside Docker with network/resource isolation."""
        if not self._build_docker_image():
            return self._run_locally(config_json)

        try:
            result = subprocess.run(
                [
                    "docker", "run",
                    "--rm",
                    "--network", "none",
                    "--memory", "512m",
                    "--cpus", "1.0",
                    "-i",
                    _DOCKER_IMAGE,
                ],
                input=config_json,
                capture_output=True,
                text=True,
                timeout=180,
            )

            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout)

            # Docker ran but script failed — fallback
            return self._run_locally(config_json)

        except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
            return self._run_locally(config_json)

    def _run_locally(self, config_json: str) -> Dict[str, Any]:
        """
        Fallback: run sandbox/run_tests.py directly in a subprocess.
        No network isolation but useful in development environments
        where Docker is unavailable.
        """
        script_path = _SANDBOX_DIR / "run_tests.py"
        try:
            result = subprocess.run(
                [sys.executable, str(script_path)],
                input=config_json,
                capture_output=True,
                text=True,
                timeout=180,
            )

            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout)

            return {
                "passed": False,
                "total": 0,
                "passed_count": 0,
                "failed_count": 1,
                "error_count": 1,
                "coverage_percent": 0.0,
                "tests": [],
                "stdout": result.stdout[-3000:],
                "stderr": result.stderr[-2000:],
            }
        except subprocess.TimeoutExpired:
            return {
                "passed": False,
                "total": 0,
                "passed_count": 0,
                "failed_count": 1,
                "error_count": 1,
                "coverage_percent": 0.0,
                "tests": [],
                "stdout": "",
                "stderr": "Test execution timed out after 180 seconds",
            }
        except Exception as exc:
            return {
                "passed": False,
                "total": 0,
                "passed_count": 0,
                "failed_count": 1,
                "error_count": 1,
                "coverage_percent": 0.0,
                "tests": [],
                "stdout": "",
                "stderr": str(exc),
            }

    def run(
        self,
        tool_code: str,
        test_code: str,
        tool_name: str,
        requirements: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Execute tests in isolation. Returns structured result dict.

        Result schema:
          passed:           bool
          total:            int
          passed_count:     int
          failed_count:     int
          error_count:      int
          coverage_percent: float
          tests:            [{name, outcome, duration, message}]
          stdout:           str
          stderr:           str
        """
        config_json = json.dumps(
            {
                "tool_code": tool_code,
                "test_code": test_code,
                "tool_name": tool_name,
                "requirements": requirements or [],
            }
        )

        if self._docker_available():
            return self._run_in_docker(config_json)
        return self._run_locally(config_json)


# ---------------------------------------------------------------------------
# BugReportGenerator
# ---------------------------------------------------------------------------

class BugReportGenerator:
    """Uses an LLM to produce a structured bug report from failing test output."""

    def __init__(self, llm: ChatOpenAI) -> None:
        self.llm = llm

    def generate(
        self,
        tool_code: str,
        test_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Generate a structured bug report.

        Returns:
          {
            "summary":        str,
            "failing_tests":  [{name, message}],
            "suggested_fixes": [str],
            "root_cause":     str,
          }
        """
        failing = [
            t for t in test_results.get("tests", []) if t.get("outcome") != "passed"
        ]

        if not failing:
            return {
                "summary": "No specific failing tests identified",
                "failing_tests": [],
                "suggested_fixes": ["Review test output for errors"],
                "root_cause": "Unknown",
            }

        failing_str = "\n".join(
            f"  [{t['name']}]:\n    {t.get('message', '')[:400]}"
            for t in failing[:10]
        )
        stdout_snippet = test_results.get("stdout", "")[-1500:]

        prompt = f"""You are a senior Python engineer debugging a generated tool.

TOOL CODE (first 2000 chars):
{tool_code[:2000]}

FAILING TESTS:
{failing_str}

PYTEST OUTPUT (last 1500 chars):
{stdout_snippet}

Analyze the failures and respond with ONLY a JSON object (no markdown):
{{
  "summary": "one-sentence summary of the root cause",
  "failing_tests": [
    {{"name": "test_name", "message": "brief failure description"}}
  ],
  "suggested_fixes": [
    "concrete fix suggestion 1",
    "concrete fix suggestion 2"
  ],
  "root_cause": "detailed explanation of what is wrong and why"
}}
"""
        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.rstrip("`").strip()
            report = json.loads(content)
            # Ensure failing_tests list is present
            if "failing_tests" not in report:
                report["failing_tests"] = [
                    {"name": t["name"], "message": t.get("message", "")}
                    for t in failing[:10]
                ]
            return report
        except Exception:
            # Fallback to a simple report on parse error
            return {
                "summary": f"{len(failing)} test(s) failed",
                "failing_tests": [
                    {"name": t["name"], "message": t.get("message", "")}
                    for t in failing[:10]
                ],
                "suggested_fixes": ["Review and fix the implementation logic"],
                "root_cause": stdout_snippet[:500],
            }


# ---------------------------------------------------------------------------
# TestingAgent
# ---------------------------------------------------------------------------

class TestingAgent:
    """
    Orchestrates the Phase 5 testing pipeline:
    1. Generates additional test cases
    2. Runs combined tests in sandbox
    3. Produces bug report on failure

    The retry / escalation loop is managed by the Celery worker layer.
    """

    def __init__(self, temperature: float = 0.2) -> None:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY not set in .env")
        self.llm = ChatOpenAI(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            temperature=temperature,
        )
        self.test_gen = TestCaseGenerator(self.llm)
        self.sandbox = SandboxRunner()
        self.bug_gen = BugReportGenerator(self.llm)

    def run_tests(
        self,
        tool_name: str,
        tool_class: str,
        tool_description: str,
        acceptance_criteria: List[str],
        tool_code: str,
        test_code: str,
        requirements: Optional[List[str]] = None,
        retry_count: int = 0,
    ) -> Dict[str, Any]:
        """
        Full testing pipeline.

        Returns:
          {
            "passed":       bool,
            "test_results": { ... sandbox result ... },
            "bug_report":   dict | None,   # None when passed
          }
        """
        # Step 1 — Generate additional tests (best effort)
        additional_tests = self.test_gen.generate_additional_tests(
            tool_name=tool_name,
            tool_class=tool_class,
            tool_description=tool_description,
            acceptance_criteria=acceptance_criteria,
            existing_test_code=test_code,
        )

        # Combine original + additional tests
        combined_test_code = test_code
        if additional_tests:
            combined_test_code = test_code + "\n\n# ── Additional LLM-generated tests ──\n" + additional_tests

        # Step 2 — Run in sandbox
        sandbox_result = self.sandbox.run(
            tool_code=tool_code,
            test_code=combined_test_code,
            tool_name=tool_name,
            requirements=requirements,
        )

        if sandbox_result["passed"]:
            return {
                "passed": True,
                "test_results": sandbox_result,
                "bug_report": None,
            }

        # Step 3 — Generate bug report
        bug_report = self.bug_gen.generate(
            tool_code=tool_code,
            test_results=sandbox_result,
        )

        return {
            "passed": False,
            "test_results": sandbox_result,
            "bug_report": bug_report,
        }


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_instance: Optional[TestingAgent] = None


def get_testing_agent() -> TestingAgent:
    """Return a lazily-initialized singleton TestingAgent."""
    global _instance
    if _instance is None:
        _instance = TestingAgent()
    return _instance
