# Garmin Workouts MCP Server - Claude Development Guide

## Project Overview

This is a Model Control Protocol (MCP) server that integrates with Garmin Connect to manage workouts through natural language. It's built with Python using FastMCP and the Garth library for Garmin authentication.

## Project Structure

```
garmin-workouts-mcp/
├── garmin_workouts_mcp/      # Main package directory
│   ├── __init__.py
│   ├── main.py              # MCP server entry point
│   └── garmin_workout.py    # Core workout logic
├── tests/                   # Test suite
│   ├── test_garmin_workout.py
│   ├── test_integration.py
│   └── test_main.py
├── pyproject.toml          # Package configuration
├── requirements.txt        # Development dependencies
├── Makefile               # Development tasks
└── README.md             # User documentation
```

## Development Commands

### Environment Setup
```bash
# Initialize development environment
make init

# Activate virtual environment
source .venv/bin/activate
```

### Testing
```bash
# Run all tests with coverage
make test

# Run tests with pytest directly
python -m pytest tests/ -v --tb=short --cov=garmin_workouts_mcp --cov-report=term-missing
```

### Code Quality
```bash
# Run linter
make lint

# Format code with ruff
ruff check . --fix
```

### Building and Release
```bash
# Build package
make build

# Prepare for release (builds and uploads to PyPI)
make release
```

## Key Components

### MCP Server (main.py)
- Entry point for the MCP server
- Defines available tools for workout management
- Handles authentication with Garmin Connect

### Garmin Workout Module (garmin_workout.py)
- Core logic for creating and managing workouts
- Interfaces with Garmin Connect API via Garth
- Handles workout structure and validation

## Important Patterns

### Authentication
- Uses environment variables: `GARMIN_EMAIL` and `GARMIN_PASSWORD`
- Alternatively uses saved credentials in `~/.garth`
- Custom location via `GARTH_HOME` environment variable

### Error Handling
- All tools should return proper error messages
- Authentication failures should be clearly communicated
- Network errors should be handled gracefully

### Testing Approach
- Unit tests for workout logic
- Integration tests for MCP server
- Mock Garmin API calls in tests
- Use pytest fixtures for common test data

## Code Conventions

### Python Style
- Follow PEP 8 guidelines
- Use type hints where applicable
- Keep functions focused and small
- Document complex logic with docstrings

### Import Order
1. Standard library imports
2. Third-party imports
3. Local application imports

### Error Messages
- Be specific about what went wrong
- Suggest corrective actions when possible
- Include relevant context (workout IDs, dates, etc.)

## Common Tasks

### Adding a New Tool
1. Define the tool in `main.py`
2. Implement the logic in `garmin_workout.py`
3. Add tests in `tests/`
4. Update README.md with usage examples

### Debugging
- Check logs for authentication issues
- Verify environment variables are set
- Test with minimal examples first
- Use pytest debugging: `pytest -vv --pdb`

## Dependencies
- **fastmcp**: MCP server framework
- **garth**: Garmin Connect authentication
- **pytest**: Testing framework
- **ruff**: Linting and formatting

## Notes
- The project uses setuptools for packaging
- CI/CD pipeline runs tests automatically
- Version is managed in `pyproject.toml`
- Credentials should never be committed