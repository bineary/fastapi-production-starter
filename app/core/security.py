import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from app.core.config import Settings
from app.models.enums import OrgRole

_pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

TokenType = Literal["access"]


class AccessTokenPayload(BaseModel):
    sub: uuid.UUID
    org: uuid.UUID
    role: OrgRole
    type: TokenType
    exp: datetime
    iat: datetime


def hash_password(plain_password: str) -> str:
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    *, user_id: uuid.UUID, organization_id: uuid.UUID, role: OrgRole, settings: Settings
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "org": str(organization_id),
        "role": role.value,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


class InvalidTokenError(Exception):
    pass


def decode_access_token(token: str, settings: Settings) -> AccessTokenPayload:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError(str(exc)) from exc

    if payload.get("type") != "access":
        raise InvalidTokenError("Not an access token")

    return AccessTokenPayload.model_validate(payload)


def create_purpose_token(
    *, user_id: uuid.UUID, purpose: str, expires_delta: timedelta, settings: Settings
) -> str:
    """A short-lived, single-purpose JWT for email verification / password
    reset links. Deliberately not stored server-side — the purpose + expiry
    baked into the token is enough to keep this a stateless stub."""
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "purpose": purpose,
        "type": "purpose",
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_purpose_token(token: str, *, expected_purpose: str, settings: Settings) -> uuid.UUID:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError(str(exc)) from exc

    if payload.get("type") != "purpose" or payload.get("purpose") != expected_purpose:
        raise InvalidTokenError("Token purpose mismatch")

    return uuid.UUID(payload["sub"])


def generate_refresh_token() -> str:
    """A high-entropy opaque token — not a JWT. Only its hash is ever stored,
    so a database read alone can't be used to impersonate a user."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()
