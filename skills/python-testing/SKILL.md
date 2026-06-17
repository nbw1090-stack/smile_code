---
name: python-testing
description: Guide for writing Python tests with pytest, including fixtures, mocking, and best practices
---

# Python Testing Guide

## Test Structure
- Use `pytest` as the test runner
- Name test files `test_<module>.py`
- Name test functions `test_<behavior>`
- Use descriptive docstrings for test cases

## Fixtures
```python
import pytest

@pytest.fixture
def sample_data():
    return {"key": "value"}

def test_with_fixture(sample_data):
    assert sample_data["key"] == "value"
```

## Mocking
- Use `unittest.mock` for external dependencies
- Prefer dependency injection over monkey-patching
- Mock at the boundary of your system

## Running Tests
- `pytest tests/ -v` for verbose output
- `pytest tests/ -k "pattern"` to filter by name
- See `scripts/run_tests.sh` for CI-compatible test runner

## References
- See `references/pytest-cheatsheet.md` for quick reference
