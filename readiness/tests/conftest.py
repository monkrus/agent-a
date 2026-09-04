"""Test-session safety net.

The sandbox this suite may run in can have a real ANTHROPIC_API_KEY set
in the ambient environment for unrelated reasons (e.g. the coding agent
running the tests). Nothing in this test suite should ever make a real,
billed Anthropic API call. SHOPPER=mock is the master switch the rest of
the codebase already respects (see shopper.ask/ask_batch); force it here
so a stray tier="paid" code path in a test can't silently start spending
real money.
"""
import os
import pytest


@pytest.fixture(autouse=True)
def _no_real_api_calls(monkeypatch):
    monkeypatch.setenv("TESTING", "1")
    monkeypatch.setenv("SHOPPER", "mock")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
