"""
Deployment and hot-reload manager for Phase 7.

Handles:
- Tracking tool deployments in the database
- Triggering hot-reload signals to load new tools
- Managing rollbacks to previous tool versions
- Recording deployment events in agent logs
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from core.database import SessionLocal
from core.models.tool_registry import ToolRegistryEntry
from core.models.agent_log import AgentLog, AgentType, AgentLogStatus


class DeploymentManager:
    """Manages tool deployments, versioning, and hot-reloads."""

    @staticmethod
    def record_deployment(
        db: Session,
        tool_name: str,
        version: str,
        previous_version: Optional[str] = None,
    ) -> dict:
        """
        Record a tool deployment in the database.

        Args:
            db: Database session
            tool_name: Name of the deployed tool
            version: New version string (e.g., "1.0.0", "main-abc1234")
            previous_version: Previous version string (for rollback)

        Returns:
            {success: bool, tool_name: str, version: str, deployed_at: datetime}
        """
        try:
            # Check if tool already exists in registry
            existing = (
                db.query(ToolRegistryEntry)
                .filter(ToolRegistryEntry.tool_name == tool_name)
                .first()
            )

            now = datetime.now(timezone.utc)

            if existing:
                # Update existing entry
                existing.previous_version = existing.version
                existing.version = version
                existing.deployed_at = now
            else:
                # Create new entry
                entry = ToolRegistryEntry(
                    tool_name=tool_name,
                    version=version,
                    previous_version=previous_version,
                    deployed_at=now,
                )
                db.add(entry)

            db.commit()

            return {
                "success": True,
                "tool_name": tool_name,
                "version": version,
                "deployed_at": now.isoformat(),
            }

        except Exception as exc:
            db.rollback()
            return {"success": False, "error": str(exc)}

    @staticmethod
    def get_deployment_history(db: Session, tool_name: str) -> dict:
        """
        Get deployment history for a tool.

        Returns:
            {
                tool_name: str,
                current_version: str,
                deployed_at: datetime,
                previous_version: str | None,
                history: [...]
            }
        """
        entry = (
            db.query(ToolRegistryEntry)
            .filter(ToolRegistryEntry.tool_name == tool_name)
            .first()
        )

        if not entry:
            return {"success": False, "error": "Tool not found in registry"}

        return {
            "success": True,
            "tool_name": entry.tool_name,
            "current_version": entry.version,
            "deployed_at": entry.deployed_at.isoformat() if entry.deployed_at else None,
            "previous_version": entry.previous_version,
            "created_at": entry.created_at.isoformat(),
            "updated_at": entry.updated_at.isoformat(),
        }

    @staticmethod
    def rollback_tool(
        db: Session,
        tool_name: str,
        requester_id: Optional[str] = None,
    ) -> dict:
        """
        Rollback a tool to its previous version.

        Args:
            db: Database session
            tool_name: Name of the tool to rollback
            requester_id: User ID requesting the rollback

        Returns:
            {success: bool, tool_name: str, rolled_back_to: str, error?: str}
        """
        try:
            entry = (
                db.query(ToolRegistryEntry)
                .filter(ToolRegistryEntry.tool_name == tool_name)
                .first()
            )

            if not entry:
                return {"success": False, "error": "Tool not found in registry"}

            if not entry.previous_version:
                return {
                    "success": False,
                    "error": "No previous version available for rollback",
                }

            # Save current version
            current_version = entry.version

            # Rollback
            entry.version = entry.previous_version
            entry.previous_version = current_version
            entry.deployed_at = datetime.now(timezone.utc)

            db.commit()

            # Log the rollback
            log_entry = AgentLog(
                agent_type=AgentType.CODING,
                action="tool_rollback",
                details={
                    "tool_name": tool_name,
                    "from_version": current_version,
                    "to_version": entry.previous_version,
                    "requester_id": requester_id,
                },
                status=AgentLogStatus.SUCCESS,
            )
            db.add(log_entry)
            db.commit()

            return {
                "success": True,
                "tool_name": tool_name,
                "rolled_back_to": entry.version,
                "previous_version": current_version,
            }

        except Exception as exc:
            db.rollback()
            return {"success": False, "error": str(exc)}

    @staticmethod
    def list_deployed_tools(db: Session) -> dict:
        """
        List all deployed tools with their current versions.

        Returns:
            {
                success: bool,
                tools: [
                    {tool_name, version, deployed_at, previous_version},
                    ...
                ]
            }
        """
        try:
            entries = db.query(ToolRegistryEntry).order_by(
                ToolRegistryEntry.deployed_at.desc()
            ).all()

            tools = [
                {
                    "tool_name": entry.tool_name,
                    "version": entry.version,
                    "deployed_at": entry.deployed_at.isoformat()
                    if entry.deployed_at
                    else None,
                    "previous_version": entry.previous_version,
                    "created_at": entry.created_at.isoformat(),
                }
                for entry in entries
            ]

            return {"success": True, "tools": tools, "count": len(tools)}

        except Exception as exc:
            return {"success": False, "error": str(exc)}
