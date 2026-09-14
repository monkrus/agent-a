"""
Test that the scanner works when private fix recipes are absent.

The public fixes.py stub must:
1. Import without error
2. Return None for passing checks
3. Return None for failing checks (no placeholder — YAML 'fix' field provides advice)
"""
import sys
import os

# Ensure readiness package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_generate_fix_returns_none_for_pass():
    from fixes import generate_fix
    result = generate_fix({"id": "RDY-001", "verdict": "PASS"}, {})
    assert result is None


def test_generate_fix_returns_none_for_fail_without_private():
    from fixes import generate_fix
    result = generate_fix({"id": "RDY-001", "verdict": "FAIL"}, {})
    # Without private module, no fix recipe — the YAML 'fix' field provides advice
    assert result is None


def test_generate_fix_returns_none_for_unknown():
    from fixes import generate_fix
    result = generate_fix({"id": "RDY-001", "verdict": "UNKNOWN"}, {})
    assert result is None
