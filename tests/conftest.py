# AdventureForge — Test Configuration
"""
pytest configuration and shared fixtures.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Pytest configuration
pytest_plugins = ["pytest_asyncio"]

def pytest_configure(config):
    """Configure pytest."""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests (require running server)"
    )
    config.addinivalue_line(
        "markers", "slow: marks tests as slow running"
    )