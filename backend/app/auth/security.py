from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.config import settings

ALGORITHM = "HS256"
_hasher = PasswordHasher()
# Verified when the email is unknown, so login takes the same time either way.
_DUMMY_HASH = _hasher.hash("not-a-real-account")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def burn_verification_time(password: str) -> None:
    verify_password(_DUMMY_HASH, password)


def create_token(user_id: int, minutes: int | None = None) -> str:
    lifetime = settings.session_minutes if minutes is None else minutes
    claims = {"sub": str(user_id), "exp": datetime.now(UTC) + timedelta(minutes=lifetime)}
    return jwt.encode(claims, settings.jwt_secret, algorithm=ALGORITHM)


def read_token(token: str) -> int | None:
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
        return int(claims["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        return None
