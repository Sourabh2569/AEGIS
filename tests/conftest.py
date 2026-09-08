from __future__ import annotations

import atexit
import os
import shutil
import tempfile

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
