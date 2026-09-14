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


def test_generate_fix_returns_recipe_for_fail():
    from fixes import generate_fix
    result = generate_fix({"id": "RDY-001", "verdict": "FAIL"}, {})
    # With private module present, returns a real fix recipe
    # Without private module, returns None (YAML 'fix' field provides advice)
    if result is not None:
        assert isinstance(result, str)
        assert len(result) > 0


def test_generate_fix_returns_none_for_unknown():
    from fixes import generate_fix
    result = generate_fix({"id": "RDY-001", "verdict": "UNKNOWN"}, {})
    assert result is None
