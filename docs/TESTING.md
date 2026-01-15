# Testing Guide for Pickleball Video Editor

This document describes the test suite structure and how to run tests.

## Test Suite Overview

The test suite is located in the `tests/` directory and covers the core business logic of the application.

### Test Files

1. **tests/test_score_state.py** (21 tests)
   - Singles scoring rules
   - Doubles scoring rules (0-0-2 start, server rotation)
   - Win conditions (win-by-2 rule)
   - Snapshot save/restore for undo
   - Score string formatting from serving team's perspective

2. **tests/test_rally_manager.py** (18 tests)
   - Rally start/end with padding (-0.5s start, +1.0s end)
   - Undo functionality (RALLY_START and RALLY_END actions)
   - Multiple rally sequences
   - Segment export format for Kdenlive
   - Frame/time conversions with different FPS

3. **tests/test_output.py** (15 tests)
   - SRT timestamp formatting (HH:MM:SS,mmm)
   - SRT subtitle generation from segments
   - Cumulative output timeline (not source frames)
   - File writing with parent directory creation

**Total: 54 tests**

## Running Tests

### Run All Tests

```bash
./run_tests.sh
```

Or directly with pytest:

```bash
source venv/bin/activate
python -m pytest tests/ -v
```

### Run Specific Test File

```bash
./run_tests.sh tests/test_score_state.py
python -m pytest tests/test_score_state.py -v
```

### Run Specific Test Class or Function

```bash
python -m pytest tests/test_score_state.py::TestScoreStateSingles -v
python -m pytest tests/test_score_state.py::TestScoreStateSingles::test_init_singles -v
```

### Run Tests with Coverage (if installed)

```bash
python -m pytest tests/ --cov=src --cov-report=html
```

## Test Fixtures

Common fixtures are defined in `tests/conftest.py`:

- `singles_score_state`: Fresh singles ScoreState instance
- `doubles_score_state`: Fresh doubles ScoreState instance
- `rally_manager`: Fresh RallyManager instance (60fps)
- `score_snapshot`: Basic ScoreSnapshot for doubles at start
- `singles_snapshot`: Basic ScoreSnapshot for singles

## Writing New Tests

### Test Structure

```python
import pytest
from src.core.some_module import SomeClass

class TestSomeFeature:
    """Test suite for some feature."""

    def test_specific_behavior(self):
        """Test that specific behavior works correctly."""
        # Arrange
        instance = SomeClass()

        # Act
        result = instance.some_method()

        # Assert
        assert result == expected_value
```

### Naming Conventions

- Test files: `test_<module_name>.py`
- Test classes: `Test<FeatureName>`
- Test methods: `test_<specific_behavior>`

### Key Testing Patterns

**1. Test Both Happy Path and Edge Cases**

```python
def test_valid_input(self):
    """Test with valid input."""
    ...

def test_invalid_input_raises_error(self):
    """Test that invalid input raises ValueError."""
    with pytest.raises(ValueError):
        ...
```

**2. Use Descriptive Names and Docstrings**

```python
def test_doubles_first_fault_sideout(self):
    """Test 0-0-2 immediate side-out rule.

    At game start (0-0-2), the first fault should cause
    immediate side-out to the other team's server 1.
    """
```

**3. Test State Mutations Explicitly**

```python
def test_server_wins_increments_score(self):
    """Test that server winning increases serving team's score."""
    state = ScoreState("singles", "11", players)
    state.server_wins()
    assert state.score == [1, 0]
    assert state.serving_team == 0  # Still serving
```

**4. Use Fixtures for Common Setup**

```python
def test_with_fixture(self, doubles_score_state):
    """Test using a pytest fixture."""
    doubles_score_state.server_wins()
    assert doubles_score_state.score == [1, 0]
```

## Testing Philosophy

### LBYL (Look Before You Leap)

Tests should verify that code checks conditions before acting:

```python
def test_end_rally_without_start_raises_error(self):
    """Test that ending rally without starting raises ValueError."""
    manager = RallyManager(fps=60.0)
    with pytest.raises(ValueError, match="No rally in progress"):
        manager.end_rally(15.0, "server", "0-0-2", snapshot)
```

### Type Safety

All test code uses modern Python 3.13 syntax:

```python
def process_segments(segments: list[dict[str, Any]]) -> list[str]:
    """Process segments and return results."""
    return [seg["score"] for seg in segments]
```

### No Mocking (Yet)

The current test suite uses real instances without mocking. This may change if:
- Tests become too slow (video processing tests)
- External dependencies are added (network calls, databases)

## CI/CD Integration

To integrate with CI/CD (GitHub Actions, GitLab CI, etc.):

```yaml
# Example .github/workflows/test.yml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.13'
      - run: pip install -r requirements.txt
      - run: python -m pytest tests/ -v
```

## Test Coverage Goals

Current coverage targets:

- Core business logic (score_state, rally_manager): **100%**
- Output generators (subtitle_generator): **90%+**
- UI components: **Manual testing** (PyQt6 requires different approach)

## Future Test Additions

When these features are implemented, add tests for:

1. **Session Management**
   - Session save/load
   - Video hash verification
   - Timestamp updates

2. **Kdenlive Generator**
   - XML structure validation
   - Playlist generation
   - Track assignments
   - Transition handling

3. **Video Integration**
   - FFprobe metadata extraction
   - MPV player state management
   - Frame-accurate seeking

4. **UI Components** (if feasible)
   - Button state changes
   - Signal/slot connections
   - Keyboard shortcuts
   - Toast notifications

## Troubleshooting

### Tests Fail with Import Errors

Ensure virtual environment is activated:

```bash
source venv/bin/activate
pip install -r requirements.txt
```

### Tests Pass Locally but Fail in CI

Check Python version consistency:

```bash
python --version  # Should be 3.13.x
```

### Slow Tests

Currently all tests run in < 1 second. If tests become slow:
- Use pytest marks to separate fast/slow tests
- Implement test parallelization with `pytest-xdist`

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [Modern Python type hints](https://docs.python.org/3/library/typing.html)
- Project design docs: `docs/DETAILED_DESIGN.md`
- Coding standards: `.claude/agents/python-coder.md`
