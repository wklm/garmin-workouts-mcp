"""Allow the package to be run as a module."""

import sys


def main():
    """Main entry point for module execution."""
    if len(sys.argv) > 1 and sys.argv[1].endswith('.md'):
        # If a markdown file is provided, run the schedule_training_plan command
        from .schedule_training_plan import main as schedule_main
        schedule_main()
    else:
        # Otherwise, run the MCP server
        from .main import main as mcp_main
        mcp_main()


if __name__ == "__main__":
    main()