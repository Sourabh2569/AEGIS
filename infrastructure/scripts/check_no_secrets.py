from __future__ import annotations

import re
from pathlib import Path


BLOCKED = re.compile(r"(ghp_|github_pat_|-----BEGIN PRIVATE KEY-----|AKIA[0-9A-Z]{16})")
ROOTS = ["apps", "packages", "docs", "tests", "sample_data", "infrastructure"]
SKIP_PARTS = {"node_modules", ".next", "__pycache__", ".pytest_cache", ".venv"}


def main() -> None:
    for root in ROOTS:
        for path in Path(root).rglob("*"):
            if path.resolve() == Path(__file__).resolve():
                continue
            if SKIP_PARTS.intersection(path.parts):
                continue
            if path.is_file() and BLOCKED.search(path.read_text(errors="ignore")):
                raise SystemExit(f"Potential secret in {path}")


if __name__ == "__main__":
    main()
