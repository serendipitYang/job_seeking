#!/bin/bash
# Full-time search. Set JOB_SEARCH_PYTHON to override the interpreter.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
if [[ -n "${JOB_SEARCH_PYTHON:-}" ]]; then
    CAREER_PYTHON="$JOB_SEARCH_PYTHON"
elif [[ -x "$SCRIPT_DIR/.venv/bin/python" ]]; then
    CAREER_PYTHON="$SCRIPT_DIR/.venv/bin/python"
else
    CAREER_PYTHON=python3
fi
if [[ "${1:-}" == "--docker" ]]; then
    shift
    exec docker compose run --rm job-search python run_job_search.py "$@"
fi
exec "$CAREER_PYTHON" run_job_search.py "$@"
