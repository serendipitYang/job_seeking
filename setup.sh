#!/bin/bash
# Setup script for Job Seeking Tool
# Creates virtual environment and installs dependencies

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Setting up Job Seeking Tool..."
echo ""

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "Python version: $PYTHON_VERSION"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

echo ""
echo "Setup complete!"
echo ""
echo "To run the job search:"
echo "  source venv/bin/activate"
echo "  python run_job_search.py"
echo ""
echo "Or use the convenience script:"
echo "  ./search_jobs.sh"
echo ""
echo "Options:"
echo "  --days N         Search jobs from last N days"
echo "  --no-similarity  Skip similarity matching (faster)"
echo "  --docker         Run using Docker"
