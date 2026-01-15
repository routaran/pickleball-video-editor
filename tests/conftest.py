"""Pytest configuration and shared fixtures.

Provides reusable fixtures for ScoreState, RallyManager, and test data.
"""

import pytest
from src.core.score_state import ScoreState
from src.core.rally_manager import RallyManager
from src.core.models import ScoreSnapshot


@pytest.fixture
def singles_score_state():
    """Create a fresh singles score state."""
    return ScoreState("singles", "11", {"team1": ["Alice"], "team2": ["Bob"]})


@pytest.fixture
def doubles_score_state():
    """Create a fresh doubles score state."""
    return ScoreState(
        "doubles", "11", {"team1": ["Alice", "Bob"], "team2": ["Carol", "Dave"]}
    )


@pytest.fixture
def rally_manager():
    """Create a fresh rally manager with 60fps."""
    return RallyManager(fps=60.0)


@pytest.fixture
def score_snapshot():
    """Create a basic score snapshot for doubles at start."""
    return ScoreSnapshot(score=(0, 0), serving_team=0, server_number=2)


@pytest.fixture
def singles_snapshot():
    """Create a basic score snapshot for singles."""
    return ScoreSnapshot(score=(0, 0), serving_team=0, server_number=None)
