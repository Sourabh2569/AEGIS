from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone

import jwt


class TokenError(Exception):
    pass


@dataclass(frozen=True)
class TokenClaims:
    username: str
    role: str


def issue_token(*, username: str, role: str, secret: str, ttl_minutes: int) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": username,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=ttl_minutes),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def verify_token(token: str, *, secret: str) -> TokenClaims:
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Invalid token.") from exc
    username = payload.get("sub")
    role = payload.get("role")
    if not username or not role:
        raise TokenError("Token is missing required claims.")
    return TokenClaims(username=username, role=role)
