"""
Health-check endpoint.
Used by Docker/k8s probes and the frontend to verify connectivity.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from core.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health", summary="Health check")
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as exc:
        db_status = f"unhealthy: {exc}"

    return {
        "status": "ok",
        "database": db_status,
    }
