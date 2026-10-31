from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.auth import security
from app.auth.models import Role, User
from app.config import settings
from app.db import get_db

SESSION_COOKIE = "dfs_session"
DbSession = Annotated[Session, Depends(get_db)]


def set_session_cookie(response: Response, user_id: int) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        security.create_token(user_id),
        max_age=settings.session_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )


def current_user(request: Request, response: Response, db: DbSession) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    user_id = security.read_token(token) if token else None
    user = db.get(User, user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    # Renewing on each request makes the 30 minutes count from the last activity (DFS-F-001).
    set_session_cookie(response, user.id)
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_roles(*roles: Role):
    """Route dependency that allows only the given roles; every other role gets 403 (DFS-SR-003)."""

    def check(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this action")
        return user

    return check
