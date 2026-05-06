"""
Phase 8: Notification Service

Sends notifications via email and Slack for:
- Task approvals needed
- PRs created
- Deployments completed
- Escalations
- Budget alerts
"""
import smtplib
import asyncio
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List
import requests

from core.config import settings


class NotificationService:
    """Service for sending notifications via email and Slack."""

    @staticmethod
    def send_email(
        to_emails: List[str],
        subject: str,
        html_body: str,
        text_body: Optional[str] = None,
    ) -> dict:
        """
        Send email notification.

        Args:
            to_emails: Recipient email addresses
            subject: Email subject
            html_body: HTML body content
            text_body: Plain text fallback

        Returns:
            {success: bool, message: str}
        """
        if not settings.enable_email_notifications:
            return {"success": False, "message": "Email notifications disabled"}

        if not settings.smtp_host or not settings.smtp_username:
            return {"success": False, "message": "SMTP not configured"}

        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = settings.notification_from_email
            msg["To"] = ", ".join(to_emails)
            msg["Date"] = datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")

            # Attach text and HTML
            if text_body:
                msg.attach(MIMEText(text_body, "plain"))
            msg.attach(MIMEText(html_body, "html"))

            # Send via SMTP
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
                server.starttls()
                server.login(settings.smtp_username, settings.smtp_password)
                server.sendmail(
                    settings.notification_from_email,
                    to_emails,
                    msg.as_string(),
                )

            return {
                "success": True,
                "message": f"Email sent to {len(to_emails)} recipients",
                "recipients": len(to_emails),
            }

        except Exception as exc:
            return {"success": False, "message": str(exc), "error": str(exc)}

    @staticmethod
    def send_slack_message(
        message: str,
        title: Optional[str] = None,
        color: str = "#439FE0",
        fields: Optional[dict] = None,
    ) -> dict:
        """
        Send Slack notification.

        Args:
            message: Main message text
            title: Optional message title
            color: Color for attachment (hex)
            fields: Optional dict of fields to display

        Returns:
            {success: bool, message: str}
        """
        if not settings.slack_webhook_url:
            return {"success": False, "message": "Slack webhook not configured"}

        try:
            payload = {
                "channel": settings.slack_channel,
                "attachments": [
                    {
                        "color": color,
                        "title": title,
                        "text": message,
                        "ts": int(datetime.now().timestamp()),
                    }
                ],
            }

            # Add fields if provided
            if fields:
                payload["attachments"][0]["fields"] = [
                    {
                        "title": k,
                        "value": str(v),
                        "short": len(str(v)) < 50,
                    }
                    for k, v in fields.items()
                ]

            response = requests.post(
                settings.slack_webhook_url,
                json=payload,
                timeout=5,
            )

            if response.status_code == 200:
                return {"success": True, "message": "Slack notification sent"}
            else:
                return {
                    "success": False,
                    "message": f"Slack returned {response.status_code}",
                }

        except Exception as exc:
            return {"success": False, "message": str(exc)}

    @staticmethod
    def notify_task_approval_needed(
        task_id: str,
        task_title: str,
        priority_score: Optional[float] = None,
    ) -> dict:
        """
        Notify admins that a task needs approval.

        Args:
            task_id: Task ID
            task_title: Task title
            priority_score: Optional priority score

        Returns:
            {success: bool, email?: dict, slack?: dict}
        """
        email_body = f"""
        <h2>Task Approval Required</h2>
        <p><strong>Task:</strong> {task_title}</p>
        <p><strong>Task ID:</strong> {task_id}</p>
        {f'<p><strong>Priority Score:</strong> {priority_score}</p>' if priority_score else ''}
        <p><a href="http://localhost:3000/tasks#task={task_id}">Review in Dashboard</a></p>
        """

        result = {}

        notification_emails = settings.get_notification_emails()
        if settings.enable_email_notifications and notification_emails:
            result["email"] = NotificationService.send_email(
                notification_emails,
                f"Task Approval Needed: {task_title}",
                email_body,
            )

        if settings.slack_webhook_url:
            result["slack"] = NotificationService.send_slack_message(
                f"Task needs approval: {task_title}",
                title="Task Approval Required",
                color="#FFA500",
                fields={
                    "Task ID": task_id,
                    **({"Priority": str(priority_score)} if priority_score else {}),
                },
            )

        return result

    @staticmethod
    def notify_pr_created(
        task_id: str,
        task_title: str,
        pr_url: str,
        pr_number: int,
    ) -> dict:
        """
        Notify admins that a PR has been created and needs review.

        Args:
            task_id: Task ID
            task_title: Task title
            pr_url: GitHub PR URL
            pr_number: PR number

        Returns:
            {success: bool, email?: dict, slack?: dict}
        """
        email_body = f"""
        <h2>Pull Request Created</h2>
        <p><strong>Task:</strong> {task_title}</p>
        <p><strong>PR #:</strong> {pr_number}</p>
        <p><a href="{pr_url}">Review on GitHub</a></p>
        <p>Code has been generated, tested, and is ready for human review.</p>
        """

        result = {}

        notification_emails = settings.get_notification_emails()
        if settings.enable_email_notifications and notification_emails:
            result["email"] = NotificationService.send_email(
                notification_emails,
                f"PR #{pr_number} Ready for Review: {task_title}",
                email_body,
            )

        if settings.slack_webhook_url:
            result["slack"] = NotificationService.send_slack_message(
                f"PR #{pr_number} created for {task_title}",
                title="Pull Request Ready for Review",
                color="#28A745",
                fields={
                    "Task ID": task_id,
                    "PR URL": pr_url,
                },
            )

        return result

    @staticmethod
    def notify_deployment_complete(
        task_id: str,
        task_title: str,
        tool_name: str,
        version: str,
    ) -> dict:
        """
        Notify admins that a deployment is complete.

        Args:
            task_id: Task ID
            task_title: Task title
            tool_name: Name of deployed tool
            version: Version/tag of deployment

        Returns:
            {success: bool, email?: dict, slack?: dict}
        """
        email_body = f"""
        <h2>Deployment Complete</h2>
        <p><strong>Task:</strong> {task_title}</p>
        <p><strong>Tool:</strong> {tool_name}</p>
        <p><strong>Version:</strong> {version}</p>
        <p>The new tool is now available to the Query Agent.</p>
        """

        result = {}

        notification_emails = settings.get_notification_emails()
        if settings.enable_email_notifications and notification_emails:
            result["email"] = NotificationService.send_email(
                notification_emails,
                f"Deployment Complete: {tool_name}",
                email_body,
            )

        if settings.slack_webhook_url:
            result["slack"] = NotificationService.send_slack_message(
                f"Tool {tool_name} deployed (v{version})",
                title="Deployment Complete",
                color="#0366D6",
                fields={
                    "Task ID": task_id,
                    "Tool": tool_name,
                    "Version": version,
                },
            )

        return result

    @staticmethod
    def notify_task_escalation(
        task_id: str,
        task_title: str,
        reason: str,
    ) -> dict:
        """
        Notify admins that a task has been escalated (agent failed).

        Args:
            task_id: Task ID
            task_title: Task title
            reason: Escalation reason

        Returns:
            {success: bool, email?: dict, slack?: dict}
        """
        email_body = f"""
        <h2>Task Escalation Alert</h2>
        <p><strong>Task:</strong> {task_title}</p>
        <p><strong>Reason:</strong> {reason}</p>
        <p><a href="http://localhost:3000/tasks#task={task_id}">View in Dashboard</a></p>
        <p>The agent encountered repeated failures on this task and requires human intervention.</p>
        """

        result = {}

        notification_emails = settings.get_notification_emails()
        if settings.enable_email_notifications and notification_emails:
            result["email"] = NotificationService.send_email(
                notification_emails,
                f"URGENT: Task Escalation - {task_title}",
                email_body,
            )

        if settings.slack_webhook_url:
            result["slack"] = NotificationService.send_slack_message(
                f"Task escalated: {task_title}",
                title="⚠️ Task Escalation Alert",
                color="#CB2431",
                fields={
                    "Task ID": task_id,
                    "Reason": reason,
                },
            )

        return result

    @staticmethod
    def notify_budget_alert(
        percent_used: float,
        daily_usage: int,
        daily_budget: int,
    ) -> dict:
        """
        Notify admins that token budget is running low.

        Args:
            percent_used: Percentage of budget used (0-100)
            daily_usage: Tokens used today
            daily_budget: Daily budget limit

        Returns:
            {success: bool, email?: dict, slack?: dict}
        """
        email_body = f"""
        <h2>Token Budget Alert</h2>
        <p><strong>Budget Used:</strong> {percent_used:.1f}%</p>
        <p><strong>Tokens Used:</strong> {daily_usage:,} / {daily_budget:,}</p>
        <p>Token budget is running low. Monitor usage to prevent service interruption.</p>
        """

        result = {}

        notification_emails = settings.get_notification_emails()
        if settings.enable_email_notifications and notification_emails:
            result["email"] = NotificationService.send_email(
                notification_emails,
                f"Budget Alert: {percent_used:.0f}% of token budget used",
                email_body,
            )

        if settings.slack_webhook_url:
            color = "#CB2431" if percent_used >= 90 else "#FFA500"
            result["slack"] = NotificationService.send_slack_message(
                f"Token budget at {percent_used:.0f}%",
                title="💰 Budget Alert",
                color=color,
                fields={
                    "Usage": f"{daily_usage:,} / {daily_budget:,}",
                    "Percent": f"{percent_used:.1f}%",
                },
            )

        return result


def get_notification_service() -> NotificationService:
    """Get NotificationService instance."""
    return NotificationService()
