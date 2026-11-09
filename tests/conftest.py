"""Shared fixtures for autocadss-mcp tests."""

import pytest


@pytest.fixture(autouse=True)
def _isolate_backend(monkeypatch):
    """Reset the backend singleton between tests."""
    import autocadss_mcp.client as client_mod
    monkeypatch.setattr(client_mod, "_backend", None)
    # Force ezdxf backend for tests (not on Windows or no AutoCAD)
    monkeypatch.setenv("AUTOCADSS_MCP_BACKEND", "ezdxf")
