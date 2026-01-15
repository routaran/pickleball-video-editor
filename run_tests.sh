#!/bin/bash
# Test runner for Pickleball Video Editor
# Runs the test suite with coverage and formatting options

set -e

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Default: run all tests
if [ $# -eq 0 ]; then
    echo "Running all tests..."
    python -m pytest tests/ -v --tb=short
else
    # Run specific test file(s)
    echo "Running specific tests: $@"
    python -m pytest "$@" -v --tb=short
fi
