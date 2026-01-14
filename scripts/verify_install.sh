#!/bin/bash
# Verify installation of Pickleball Video Editor dependencies

set -e

echo "=========================================="
echo "Pickleball Video Editor - Verify Install"
echo "=========================================="
echo

# Check Python version
echo "1. Checking Python version..."
PYTHON_VERSION=$(python --version 2>&1 | awk '{print $2}')
echo "   Found: Python $PYTHON_VERSION"

if ! python -c "import sys; sys.exit(0 if sys.version_info >= (3, 13) else 1)"; then
    echo "   ✗ ERROR: Python 3.13+ required"
    exit 1
fi
echo "   ✓ Python version OK"
echo

# Check system dependencies
echo "2. Checking system dependencies..."

if command -v mpv &> /dev/null; then
    echo "   ✓ mpv installed: $(mpv --version | head -n1)"
else
    echo "   ✗ mpv not found. Install with: sudo pacman -S mpv"
fi

if command -v ffmpeg &> /dev/null; then
    echo "   ✓ ffmpeg installed: $(ffmpeg -version | head -n1)"
else
    echo "   ✗ ffmpeg not found. Install with: sudo pacman -S ffmpeg"
fi
echo

# Check Python packages
echo "3. Checking Python packages..."

check_package() {
    if python -c "import $1" 2>/dev/null; then
        VERSION=$(python -c "import $1; print(getattr($1, '__version__', 'unknown'))")
        echo "   ✓ $1 ($VERSION)"
        return 0
    else
        echo "   ✗ $1 not installed"
        return 1
    fi
}

ALL_INSTALLED=true

check_package "PyQt6" || ALL_INSTALLED=false
check_package "mpv" || ALL_INSTALLED=false
check_package "lxml" || ALL_INSTALLED=false

echo

if [ "$ALL_INSTALLED" = false ]; then
    echo "Missing packages. Install with:"
    echo "  pip install -r requirements.txt"
    exit 1
fi

# Test application import
echo "4. Testing application import..."
if python -c "import src; print(f'Package version: {src.__version__}')" 2>/dev/null; then
    echo "   ✓ Application package imports successfully"
else
    echo "   ✗ Failed to import application package"
    exit 1
fi
echo

# Test basic application run
echo "5. Testing application entry point..."
if python -m src.main > /dev/null 2>&1; then
    echo "   ✓ Application runs without errors"
else
    echo "   ✗ Application failed to run"
    exit 1
fi
echo

echo "=========================================="
echo "✓ All checks passed!"
echo "=========================================="
echo
echo "Run the application with:"
echo "  python -m src.main"
echo
echo "Or after 'pip install -e .':"
echo "  pickleball-editor"
