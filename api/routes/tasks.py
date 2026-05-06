"""
Tasks routes — Phase 1 stub.
Returns empty collections with correct shapes so the frontend can integrate.
Full implementation in Phase 2 (Task Manager Agent).
"""
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import get_current_user
from core.database import get_db
from core.models.user import User

router = APIRouter()


@router.get("", summary="List tasks (Phase 2 will implement filtering/pagination)")
def list_tasks(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return {"tasks": [], "total": 0}
