#!/usr/bin/env python3
"""
AdventureForge — Test Runner
Run all tests with proper configuration.
"""

import sys
import subprocess
from pathlib import Path


def run_tests(test_type: str = "all", verbose: bool = True, coverage: bool = False):
    """Run tests with pytest."""
    cmd = ["python3", "-m", "pytest"]

    if verbose:
        cmd.append("-v")

    if coverage:
        cmd.extend(["--cov=tools", "--cov=app", "--cov=engine_pygame", "--cov-report=term-missing"])

    if test_type == "unit":
        cmd.extend(["-m", "not integration"])
    elif test_type == "integration":
        cmd.extend(["-m", "integration"])
    elif test_type == "tools":
        cmd.append("tests/test_tools.py")
    elif test_type == "engine":
        cmd.append("tests/test_engine.py")
    elif test_type == "api":
        cmd.append("tests/test_api.py")

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=Path(__file__).parent)
    return result.returncode


def main():
    import argparse
    parser = argparse.ArgumentParser(description="AdventureForge Test Runner")
    parser.add_argument(
        "type",
        nargs="?",
        default="all",
        choices=["all", "unit", "integration", "tools", "engine", "api"],
        help="Type of tests to run"
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="Less verbose output")
    parser.add_argument("--coverage", action="store_true", help="Run with coverage report")

    args = parser.parse_args()

    exit_code = run_tests(
        test_type=args.type,
        verbose=not args.quiet,
        coverage=args.coverage
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()