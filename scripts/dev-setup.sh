#!/usr/bin/env bash
set -euo pipefail

# Garmin Workouts MCP Development Setup Script
# This script sets up the development environment for the project

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "Setting up Garmin Workouts MCP development environment..."
echo "Project root: $PROJECT_ROOT"

# Change to project root
cd "$PROJECT_ROOT"

# Check Python version
echo "Checking Python version..."
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
REQUIRED_VERSION="3.10"

if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)"; then
    echo "Error: Python 3.10 or higher is required. Found: $PYTHON_VERSION"
    exit 1
fi
echo "✓ Python $PYTHON_VERSION is compatible"

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Install the package in development mode
echo "Installing package in development mode..."
pip install -e .

# Run linter
echo "Running linter..."
if command -v ruff &> /dev/null; then
    ruff check . || echo "⚠ Linting issues found (non-blocking)"
else
    echo "⚠ Ruff not found, skipping linting"
fi

# Run tests
echo "Running tests..."
if python -m pytest tests/ -v --tb=short; then
    echo "✓ All tests passed"
else
    echo "⚠ Some tests failed (non-blocking)"
fi

echo ""
echo "========================================="
echo "Development environment setup complete!"
echo "========================================="
echo ""
echo "To activate the virtual environment, run:"
echo "  source .venv/bin/activate"
echo ""
echo "Common commands:"
echo "  make test     - Run tests"
echo "  make lint     - Run linter"
echo "  make build    - Build package"
echo "  make release  - Build and upload to PyPI"
echo ""
echo "For more information, see CLAUDE.md"