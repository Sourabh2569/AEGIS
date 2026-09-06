from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class UserStoreError(Exception):
    pass


@dataclass(frozen=True)
class UserRecord:
    username: str
    password_hash: str
    role: str


def load_users(*, users_file: str = "", users_json: str = "") -> dict[str, UserRecord]:
    """Load user credentials from a local file or inline JSON env var.

    Never returns fabricated or default users -- an empty/unconfigured store
    means every login attempt fails closed. See
    docs/security/authentication.md and infrastructure/scripts/hash_password.py
    for how to provision real credentials.
    """
    raw: str | None = None
    if users_file:
        path = Path(users_file)
        if not path.exists():
            raise UserStoreError(f"AUTH_USERS_FILE not found: {users_file}")
        raw = path.read_text()
    elif users_json:
        raw = users_json

    if not raw:
        return {}

    try:
        entries = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise UserStoreError(f"Invalid auth users JSON: {exc}") from exc

    users: dict[str, UserRecord] = {}
    for entry in entries:
        try:
            record = UserRecord(
                username=entry["username"],
                password_hash=entry["password_hash"],
                role=entry["role"],
            )
        except KeyError as exc:
            raise UserStoreError(f"Auth user entry missing required field: {exc}") from exc
        users[record.username] = record
    return users
