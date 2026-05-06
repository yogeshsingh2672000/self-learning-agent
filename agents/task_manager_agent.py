"""
Task Manager Agent — Phase 3

Responsibilities:
1. De-duplicate similar tasks via semantic similarity
2. Calculate priority score via LLM (frequency + complexity + vote_count)
3. Enrich tasks with: acceptance criteria, estimated effort, required tools
4. Set task status to pending_approval before handing off to humans

This agent is invoked either:
- Automatically when a capability gap is detected by the Query Agent
- Manually via POST /api/tasks/process
"""
import json
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from core.config import settings


# ---------------------------------------------------------------------------
# Priority calculator
# ---------------------------------------------------------------------------

class PriorityCalculator:
    """
    Uses LLM to assign a priority score (0.0 – 10.0) to a task.

    Score is based on:
    - frequency: how often similar gaps appeared
    - complexity: effort to implement
    - user_votes: explicit community interest
    - impact: how much it would improve the platform
    """

    def __init__(self, llm: ChatOpenAI):
        self.llm = llm

    def calculate(
        self,
        title: str,
        description: str,
        frequency: int = 1,
        vote_count: int = 0,
    ) -> Dict[str, Any]:
        """
        Returns:
            {
                "priority_score": float,   # 0–10
                "rationale": str,          # why this score
                "estimated_effort": str,   # "small" | "medium" | "large"
            }
        """
        prompt = f"""You are a technical product manager evaluating a feature request.

TASK TITLE: {title}

DESCRIPTION:
{description}

ADDITIONAL CONTEXT:
- Times this gap appeared: {frequency}
- Community upvotes: {vote_count}

Score this task on a scale from 0.0 (lowest) to 10.0 (highest) priority,
considering: user impact, implementation complexity, and how often it is needed.

Return ONLY valid JSON with no markdown:
{{
    "priority_score": <float 0-10>,
    "rationale": "<2-3 sentence explanation>",
    "estimated_effort": "<small|medium|large>"
}}"""

        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            return json.loads(content)
        except Exception:
            # Safe fallback
            return {
                "priority_score": 5.0,
                "rationale": "Default priority assigned – LLM evaluation unavailable.",
                "estimated_effort": "medium",
            }


# ---------------------------------------------------------------------------
# Deduplication checker
# ---------------------------------------------------------------------------

class DuplicateDetector:
    """
    Detects whether a new task is semantically similar to an existing one.
    Uses LLM comparison (no vector DB required for Phase 3).
    """

    def __init__(self, llm: ChatOpenAI):
        self.llm = llm

    def find_duplicate(
        self,
        new_title: str,
        new_description: str,
        existing_tasks: List[Dict[str, Any]],
    ) -> Optional[str]:
        """
        Returns the ID of a duplicate task if one is found, else None.

        Args:
            new_title: Title of the incoming task
            new_description: Description of the incoming task
            existing_tasks: List of {"id", "title", "description"} dicts
        """
        if not existing_tasks:
            return None

        candidates = "\n".join(
            f"ID: {t['id']}\nTitle: {t['title']}\nDescription: {t['description'][:200]}"
            for t in existing_tasks
        )

        prompt = f"""Compare this NEW task against EXISTING tasks and determine if any existing task covers the same capability request.

NEW TASK:
Title: {new_title}
Description: {new_description}

EXISTING TASKS:
{candidates}

If any existing task is semantically equivalent (same feature/tool being requested), return its ID.
If none match, return null.

Return ONLY valid JSON with no markdown:
{{
    "duplicate_id": "<uuid string or null>",
    "reason": "<why it is or is not a duplicate>"
}}"""

        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            result = json.loads(content)
            return result.get("duplicate_id")
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Acceptance criteria generator
# ---------------------------------------------------------------------------

class AcceptanceCriteriaGenerator:
    """Generates structured acceptance criteria for a task using LLM."""

    def __init__(self, llm: ChatOpenAI):
        self.llm = llm

    def generate(self, title: str, description: str) -> List[str]:
        """Returns a list of acceptance criteria strings."""
        prompt = f"""Generate 3–5 clear, testable acceptance criteria for this development task.

TASK: {title}

DESCRIPTION:
{description}

Each criterion should be specific and verifiable.
Return ONLY a valid JSON array of strings with no markdown:
["criterion 1", "criterion 2", ...]"""

        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            criteria = json.loads(content)
            if isinstance(criteria, list):
                return criteria
        except Exception:
            pass

        return [
            f"Implement the {title} capability",
            "Add unit tests with ≥80% coverage",
            "Document the new tool in the registry",
            "Verify integration with the Query Agent",
        ]


# ---------------------------------------------------------------------------
# TaskManagerAgent
# ---------------------------------------------------------------------------

class TaskManagerAgent:
    """
    Orchestrates the full task enrichment pipeline:

    1. Deduplication  — merge or skip if a similar task exists
    2. Prioritisation — LLM-calculated priority score
    3. Enrichment     — acceptance criteria + effort estimate
    4. Persistence    — saves/updates to DB via the provided db session

    Call process_task() from the API route after a gap is detected.
    """

    def __init__(self, llm_provider: str = "openai", temperature: float = 0.3):
        self.llm = self._init_llm(llm_provider, temperature)
        self.priority_calc = PriorityCalculator(self.llm)
        self.dedup = DuplicateDetector(self.llm)
        self.criteria_gen = AcceptanceCriteriaGenerator(self.llm)

    def _init_llm(self, provider: str, temperature: float) -> ChatOpenAI:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY not set in .env")
        return ChatOpenAI(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            temperature=temperature,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_task(
        self,
        title: str,
        description: str,
        requested_by: str,
        required_capabilities: Optional[List[str]] = None,
        existing_tasks: Optional[List[Dict[str, Any]]] = None,
        current_vote_count: int = 0,
    ) -> Dict[str, Any]:
        """
        Full pipeline: dedup → prioritise → enrich.

        Returns a dict ready to be applied to a Task ORM object:
        {
            "is_duplicate": bool,
            "duplicate_id": str | None,
            "priority_score": float,
            "rationale": str,
            "estimated_effort": str,
            "acceptance_criteria": str,   # JSON-encoded list
            "required_capabilities": list,
        }
        """
        # 1. Deduplication
        duplicate_id = self.dedup.find_duplicate(
            title, description, existing_tasks or []
        )

        if duplicate_id:
            return {
                "is_duplicate": True,
                "duplicate_id": duplicate_id,
                "priority_score": None,
                "rationale": None,
                "estimated_effort": None,
                "acceptance_criteria": None,
                "required_capabilities": required_capabilities or [],
            }

        # 2. Priority scoring
        priority_result = self.priority_calc.calculate(
            title=title,
            description=description,
            frequency=1,
            vote_count=current_vote_count,
        )

        # 3. Acceptance criteria
        criteria = self.criteria_gen.generate(title, description)

        return {
            "is_duplicate": False,
            "duplicate_id": None,
            "priority_score": priority_result["priority_score"],
            "rationale": priority_result["rationale"],
            "estimated_effort": priority_result["estimated_effort"],
            "acceptance_criteria": json.dumps(criteria),
            "required_capabilities": required_capabilities or [],
        }

    def recalculate_priority(
        self,
        task_id: str,
        title: str,
        description: str,
        vote_count: int,
        frequency: int = 1,
    ) -> Dict[str, Any]:
        """
        Re-run priority calculation (e.g. after new votes).
        Returns updated priority_score, rationale, estimated_effort.
        """
        return self.priority_calc.calculate(
            title=title,
            description=description,
            frequency=frequency,
            vote_count=vote_count,
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_instance: Optional[TaskManagerAgent] = None


def get_task_manager_agent() -> TaskManagerAgent:
    """Return a singleton TaskManagerAgent (lazy init)."""
    global _instance
    if _instance is None:
        _instance = TaskManagerAgent()
    return _instance
