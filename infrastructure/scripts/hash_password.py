"""Generate a bcrypt-hashed user entry for AUTH_USERS_FILE / AUTH_USERS_JSON.

Never commit the output anywhere near source control -- paste it into a
local, gitignored users file (see .env.example: AUTH_USERS_FILE) or into a
deployment secret.

Usage:
    PYTHONPATH=packages/auth python infrastructure/scripts/hash_password.py
"""

from __future__ import annotations

import getpass
import json

from aegis.auth.hashing import hash_password

VALID_ROLES = {
    "FOUNDER",
    "DATA_STEWARD",
    "RESEARCHER",
    "RISK_REVIEWER",
    "PAPER_TRADING_OPERATOR",
    "ENGINEER",
    "READ_ONLY",
    "SYSTEM_SERVICE",
}


def main() -> None:
    username = input("Username: ").strip()
    role = input(f"Role ({'/'.join(sorted(VALID_ROLES))}): ").strip().upper()
    if role not in VALID_ROLES:
        raise SystemExit(f"Unknown role: {role}")
    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        raise SystemExit("Passwords do not match.")
    if len(password) < 12:
        raise SystemExit("Use a password of at least 12 characters.")

    entry = {"username": username, "password_hash": hash_password(password), "role": role}
    print("\nAdd this object to the JSON array in your AUTH_USERS_FILE:\n")
    print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
