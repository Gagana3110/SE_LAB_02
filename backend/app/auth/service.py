from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import security
from app.auth.models import PasswordResetToken, Role, User
from app.config import settings

import hashlib
import logging
import secrets

from app.notifications.email import send_email

MAX_FAILED_LOGINS = 5
log = logging.getLogger(__name__)
LOCK_MINUTES = 15


class EmailAlreadyUsed(Exception):
    pass


def _is_locked(user: User, now: datetime) -> bool:
    if user.locked_until is None:
        return False
    locked_until = user.locked_until
    if locked_until.tzinfo is None:  # SQLite drops the timezone
        locked_until = locked_until.replace(tzinfo=UTC)
    return locked_until > now


def authenticate(db: Session, email: str, password: str) -> User | None:
    """Returns the user, or None for any failure so callers cannot reveal which one it was."""
    user = db.scalar(select(User).where(User.email == email.lower()))
    if user is None:
        security.burn_verification_time(password)
        return None

    now = datetime.now(UTC)
    if _is_locked(user, now):
        security.burn_verification_time(password)
        return None

    if not security.verify_password(user.password_hash, password):
        user.failed_logins += 1
        if user.failed_logins >= MAX_FAILED_LOGINS:
            user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
            user.failed_logins = 0
        db.commit()
        return None

    user.failed_logins = 0
    user.locked_until = None
    db.commit()
    return user


def create_user(db: Session, email: str, password: str, role: Role) -> User:
    user = User(email=email.lower(), password_hash=security.hash_password(password), role=role)
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise EmailAlreadyUsed from exc
    db.refresh(user)
    return user


def list_users(db: Session) -> list[User]:
    return list(db.scalars(select(User).order_by(User.id)))


def bootstrap_admin(db: Session) -> None:
    """Creates the first Administrator from configuration, since only admins can add users."""
    if not (settings.admin_email and settings.admin_password):
        return
    if db.scalar(select(User.id).where(User.role == Role.ADMINISTRATOR).limit(1)) is None:
        create_user(db, settings.admin_email, settings.admin_password, Role.ADMINISTRATOR)

class InvalidResetLink(Exception):
    pass


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)  # SQLite drops the timezone


def request_password_reset(db: Session, email: str) -> None:
    """Emails a single-use link. Unknown emails do nothing, so nobody can probe for accounts."""
    user = db.scalar(select(User).where(User.email == email.lower()))
    if user is None:
        return
    token = secrets.token_urlsafe(32)
    expires = datetime.now(UTC) + timedelta(minutes=settings.reset_minutes)
    db.add(PasswordResetToken(user_id=user.id, token_hash=_hash_token(token), expires_at=expires))
    db.commit()
    link = f"{settings.app_base_url}/reset-password?token={token}"
    body = (f"Use this link to choose a new password. It works once and expires in "
            f"{settings.reset_minutes} minutes:\n\n{link}\n")
    try:
        send_email(user.email, "Reset your DFS password", body)
    except OSError:
        log.exception("Could not send the password reset email")


def reset_password(db: Session, token: str, new_password: str) -> None:
    record = db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == _hash_token(token))
    )
    now = datetime.now(UTC)
    if record is None or record.used_at is not None or _aware(record.expires_at) <= now:
        raise InvalidResetLink
    user = db.get(User, record.user_id)
    user.password_hash = security.hash_password(new_password)
    user.failed_logins = 0
    user.locked_until = None
    record.used_at = now
    db.commit()
