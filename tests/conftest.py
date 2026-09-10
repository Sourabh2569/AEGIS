from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile

import pytest

# `from aegis_api.main import app` (used by every integration test) imports
# the real application module, whose paper-trading/object-store state lives
# in real files under work/ by default -- the same files the dev server
# uses. Without this, every test run permanently leaves test-only
# portfolios, intents, and frozen-by-design test fixtures in real data
# (confirmed: repeated runs of test_sprint3_paper_api.py left over a dozen
# frozen test portfolios sitting in work/paper_trading.sqlite). Setting this
# before any test module is collected/imported points the whole test
# session at an isolated temp directory instead. Must happen here, in the
# top-level conftest.py, since pytest loads conftest.py files before
# importing test modules in their directories.
_work_dir = tempfile.mkdtemp(prefix="aegis-test-work-")
os.environ["AEGIS_WORK_DIR"] = _work_dir
atexit.register(shutil.rmtree, _work_dir, ignore_errors=True)

# Settings.from_env() auto-loads a real .env if one is present (so
# `make run-api` works without the operator remembering to `source .env`
# first) -- but tests rely on the plain code defaults for provider/
# data-source config to exercise fail-closed behavior, and a developer's
# real .env (e.g. MARKET_DATA_PROVIDER_NAME=kite_connect,
# DATA_SOURCE_MODE=LIVE_READONLY) would silently defeat that. Set before
# any test module is collected/imported, same as AEGIS_WORK_DIR above.
os.environ["AEGIS_SKIP_DOTENV"] = "1"


@pytest.fixture(autouse=True)
def _reset_login_rate_limiter() -> None:
    """login_rate_limiter is a module-level singleton like paper_repo --
    without this, real login failures recorded by one test file could
    accumulate and unexpectedly 429 an unrelated test using the same
    username later in the same pytest session. Guarded on the module
    already being imported so this never forces aegis_api.main's heavy
    FastAPI/SQLite setup onto unit tests that don't touch the API at all."""
    main_module = sys.modules.get("aegis_api.main")
    if main_module is not None:
        main_module.login_rate_limiter._failures_by_username.clear()
