#!/bin/bash
# CI-compatible test runner for Python projects
set -e
cd "$(dirname "$0")/../.."
echo "Running tests..."
python -m pytest tests/ -v --tb=short "$@"
