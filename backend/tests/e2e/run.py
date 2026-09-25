"""
Runs the end-to-end suites against a throwaway stack.

    # stack with the stand-in model (no Ollama needed), on port 3107
    APP_PORT=3107 docker compose -p datum-e2e -f compose.yaml -f compose.fake-llm.yaml up --build -d
    python3 backend/tests/e2e/run.py core welding jobs

    # stack with the real model (Ollama running on the host)
    APP_PORT=3107 docker compose -p datum-e2e -f compose.yaml up --build -d
    python3 backend/tests/e2e/run.py real

    docker compose -p datum-e2e down -v     # remove the test stack and its data

Never point this at a stack with data you care about: it creates the named
test accounts and libraries on it.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from client import Results  # noqa: E402
from suites import SUITES  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("suites", nargs="*", default=["core", "welding", "jobs"], choices=list(SUITES))
    parser.add_argument("--base", default="http://127.0.0.1:3107")
    parser.add_argument("--project", default="datum-e2e", help="compose project name of the stack under test")
    args = parser.parse_args()
    results = Results()
    for name in args.suites:
        print(f"\n== {name}")
        started = time.time()
        SUITES[name](args.base, results, args.project)
        print(f"   ({time.time() - started:.0f}s)")
    print(f"\n{results.passed} passed, {len(results.failures)} failed")
    for failure in results.failures:
        print(f"  FAIL {failure}")
    sys.exit(1 if results.failures else 0)


if __name__ == "__main__":
    main()
