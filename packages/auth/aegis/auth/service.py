from __future__ import annotations

from dataclasses import dataclass

from aegis.auth.hashing import verify_password
from aegis.auth.tokens import TokenError, issue_token, verify_token
from aegis.auth.users import load_users


@dataclass(frozen=True)
class AuthenticatedUser:
    username: str
    role: str


class AuthService:
    """The only supported source of truth for who is making a request.

    Deliberately separate from the legacy X-AEGIS-Role header, which any
    caller could set to any value -- see require_role() in main.py for how
    the two interact and why the header alone is never trusted outside
    development/test.
    """

    def __init__(
        self,
        *,
        jwt_secret: str,
        ttl_minutes: int,
        users_file: str = "",
        users_json: str = "",
    ) -> None:
        self._jwt_secret = jwt_secret
        self._ttl_minutes = ttl_minutes
        self._users = load_users(users_file=users_file, users_json=users_json)

    def authenticate(self, username: str, password: str) -> AuthenticatedUser | None:
        record = self._users.get(username)
        if record is None:
            return None
        if not verify_password(password, record.password_hash):
            return None
        return AuthenticatedUser(username=record.username, role=record.role)

    def issue_token(self, user: AuthenticatedUser) -> str:
        return issue_token(
            username=user.username,
            role=user.role,
            secret=self._jwt_secret,
            ttl_minutes=self._ttl_minutes,
        )

    def verify(self, token: str) -> AuthenticatedUser:
        claims = verify_token(token, secret=self._jwt_secret)
        return AuthenticatedUser(username=claims.username, role=claims.role)
