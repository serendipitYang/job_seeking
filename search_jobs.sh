#!/bin/bash
# Job Search Tool - Convenience Script
#
# Usage:
#   ./search_jobs.sh              # Run with default settings (7 days)
#   ./search_jobs.sh --days 3     # Search jobs from last 3 days
#   ./search_jobs.sh --docker     # Run using Docker
#   ./search_jobs.sh --help       # Show help

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

USE_DOCKER=false
EXTRA_ARGS=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --docker)
            USE_DOCKER=true
            shift
            ;;
        --help|-h)
            echo "Job Search Tool"
            echo ""
            echo "Usage: ./search_jobs.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --days N       Search jobs from last N days (default: 7)"
            echo "  --docker       Run using Docker container"
            echo "  --no-similarity Skip similarity matching (faster)"
            echo "  --verbose, -v  Enable verbose output"
            echo "  --help, -h     Show this help message"
            echo ""
            echo "Examples:"
            echo "  ./search_jobs.sh                    # Default 7-day search"
            echo "  ./search_jobs.sh --days 3           # Last 3 days only"
            echo "  ./search_jobs.sh --docker --days 5  # Use Docker, 5 days"
            exit 0
            ;;
        *)
            EXTRA_ARGS="$EXTRA_ARGS $1"
            shift
            ;;
    esac
done

if [ "$USE_DOCKER" = true ]; then
    echo "Running with Docker..."

    # Build if needed
    if ! docker images | grep -q "job_seeking"; then
        echo "Building Docker image..."
        docker-compose build
    fi

    # Run with Docker
    docker-compose run --rm job-search python run_job_search.py $EXTRA_ARGS
else
    echo "Running locally..."

    # Check Python
    if ! command -v python3 &> /dev/null; then
        echo "Error: Python 3 is required but not found."
        exit 1
    fi

    # Check if virtual environment exists
    if [ -d "venv" ]; then
        source venv/bin/activate
    fi

    # Run the search
    python3 run_job_search.py $EXTRA_ARGS
fi
