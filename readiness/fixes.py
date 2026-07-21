#!/usr/bin/env python3
"""
fixes.py — Stub for fix recipe generation.

Full copy-paste fix recipes are part of the paid report and live in the
agent-a-private repository.  This stub keeps the public scanner running:
generate_fix() returns a placeholder when recipes are not installed.

To enable full recipes, set the FIXES_MODULE env var to the import path of
the private recipes module, or place a _fixes_private.py alongside this file.
"""
from __future__ import annotations

import importlib
import os


def _load_private():
    """Try to load the private fix-recipe module."""
    # 1. Env-var override
    mod_path = os.environ.get("FIXES_MODULE")
    if mod_path:
        try:
            return importlib.import_module(mod_path)
        except ImportError:
            pass

    # 2. Co-located private file
    try:
        from . import _fixes_private
        return _fixes_private
    except ImportError:
        pass

    return None


_private = _load_private()

_PLACEHOLDER = (
    "Detailed fix recipe available in the full report.\n"
    "Contact sergeigodev@gmail.com for the complete agent-readiness audit."
)


def generate_fix(check_result: dict, page: dict) -> str | None:
    """Return a fix recipe for a failing check, or None if it passed."""
    if check_result.get("verdict") != "FAIL":
        return None

    if _private and hasattr(_private, "generate_fix"):
        return _private.generate_fix(check_result, page)

    return _PLACEHOLDER
