# Testing Guide - Haverford IFL

Complete guide for running, writing, and maintaining tests for the Haverford IFL application.

## 📋 Table of Contents

1. [Getting Started](#getting-started)
2. [Running Tests](#running-tests)
3. [Test Structure](#test-structure)
4. [Writing Tests](#writing-tests)
5. [Coverage Reports](#coverage-reports)
6. [CI/CD Integration](#cicd-integration)
7. [Troubleshooting](#troubleshooting)

---

## 🚀 Getting Started

### Install Testing Dependencies

```bash
# Make sure you're in the project directory
cd c:\Users\fejir\OneDrive\Documents\Project\Haverford-IFL

# Install all dependencies including test tools
pip install -r requirements.txt
```

### Verify Installation

```bash
pytest --version
# Should output: pytest 8.x.x or higher
```

---

## 🧪 Running Tests

### Run All Tests

```bash
pytest
```

### Run with Verbose Output

```bash
pytest -v
```

### Run Specific Test File

```bash
pytest tests/test_security.py
```

### Run Specific Test Class

```bash
pytest tests/test_auth.py::TestLoginFlow
```

### Run Specific Test Function

```bash
pytest tests/test_auth.py::TestLoginFlow::test_login_success
```

### Run Tests by Marker

```bash
# Run only unit tests (fast)
pytest -m unit

# Run only integration tests
pytest -m integration

# Run only security tests
pytest -m security

# Run only authentication tests
pytest -m auth

# Exclude slow tests
pytest -m "not slow"
```

### Run with Coverage

```bash
# Basic coverage report
pytest --cov

# Detailed coverage with HTML report
pytest --cov=. --cov-report=html

# Coverage for specific module
pytest --cov=security --cov-report=term-missing
```

### Run Tests in Parallel (Faster)

```bash
# Install pytest-xdist
pip install pytest-xdist

# Run tests using all CPU cores
pytest -n auto

# Run tests using 4 workers
pytest -n 4
```

### Stop on First Failure

```bash
pytest -x
```

### Run Last Failed Tests

```bash
pytest --lf
```

---

## 📁 Test Structure

```
tests/
├── conftest.py              # Shared fixtures and configuration
├── test_functions.py        # Unit tests for utility functions
├── test_security.py         # Security middleware and utilities tests
├── test_api.py              # API endpoint integration tests
└── test_auth.py             # Authentication and authorization tests
```

### Test Organization

Tests are organized by:
- **Unit tests** (`@pytest.mark.unit`): Fast, isolated tests
- **Integration tests** (`@pytest.mark.integration`): Tests with dependencies
- **Security tests** (`@pytest.mark.security`): Security-focused tests
- **Auth tests** (`@pytest.mark.auth`): Authentication/authorization tests

---

## ✍️ Writing Tests

### Basic Test Structure

```python
import pytest

@pytest.mark.unit
def test_something():
    """Test description goes here."""
    # Arrange
    expected = 5

    # Act
    result = 2 + 3

    # Assert
    assert result == expected
```

### Using Fixtures

```python
@pytest.mark.unit
def test_with_fixture(client):
    """Test using the test client fixture."""
    response = client.get("/health")
    assert response.status_code == 200
```

### Async Tests

```python
@pytest.mark.asyncio
async def test_async_function():
    """Test async functions."""
    result = await some_async_function()
    assert result is not None
```

### Mocking External Dependencies

```python
from unittest.mock import patch, Mock

@pytest.mark.unit
def test_with_mock():
    """Test with mocked external service."""
    with patch('module.external_api_call') as mock_api:
        mock_api.return_value = {'status': 'success'}

        result = function_that_calls_api()

        assert result['status'] == 'success'
        mock_api.assert_called_once()
```

### Testing Exceptions

```python
@pytest.mark.unit
def test_raises_exception():
    """Test that function raises expected exception."""
    with pytest.raises(ValueError, match="Invalid input"):
        function_that_raises("invalid")
```

### Parametrized Tests

```python
@pytest.mark.parametrize("input,expected", [
    ("test@example.com", True),
    ("invalid-email", False),
    ("", False),
])
def test_email_validation(input, expected):
    """Test email validation with multiple inputs."""
    result = validate_email(input)
    assert result == expected
```

---

## 📊 Coverage Reports

### View Coverage in Terminal

```bash
pytest --cov=. --cov-report=term-missing
```

Output example:
```
Name                    Stmts   Miss  Cover   Missing
-----------------------------------------------------
app.py                    150     10    93%   45-50, 120
security.py                80      5    94%   75-79
functions.py               45      2    96%   38, 42
-----------------------------------------------------
TOTAL                     275     17    94%
```

### Generate HTML Coverage Report

```bash
pytest --cov=. --cov-report=html
```

Then open `htmlcov/index.html` in your browser for interactive report.

### Coverage Goals

- **Minimum:** 70% overall coverage
- **Target:** 80%+ overall coverage
- **Critical modules:** 90%+ coverage (auth, security)

### Check Coverage Threshold

```bash
pytest --cov=. --cov-fail-under=70
```

---

## 🔄 CI/CD Integration

### GitHub Actions Configuration

Create `.github/workflows/tests.yml`:

```yaml
name: Tests

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main, develop ]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.9'

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt

    - name: Run tests with coverage
      env:
        FIREBASE_CONFIG: ${{ secrets.FIREBASE_CONFIG }}
        SECRET_KEY: ${{ secrets.SECRET_KEY }}
        ENVIRONMENT: testing
      run: |
        pytest --cov=. --cov-report=xml --cov-report=term

    - name: Upload coverage to Codecov
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
        fail_ci_if_error: false

    - name: Check coverage threshold
      run: |
        pytest --cov=. --cov-fail-under=70
```

### Pre-commit Hook

Create `.git/hooks/pre-commit`:

```bash
#!/bin/bash

echo "Running tests before commit..."

# Run tests
pytest -x -m "not slow"

# Check exit code
if [ $? -ne 0 ]; then
    echo "❌ Tests failed. Commit aborted."
    exit 1
fi

echo "✅ Tests passed."
exit 0
```

Make it executable:
```bash
chmod +x .git/hooks/pre-commit
```

---

## 🐛 Troubleshooting

### Common Issues

#### 1. Import Errors

**Problem:** `ModuleNotFoundError: No module named 'app'`

**Solution:**
```bash
# Make sure you're in the project root
cd c:\Users\fejir\OneDrive\Documents\Project\Haverford-IFL

# Run tests from project root
pytest
```

#### 2. Firebase Connection Errors

**Problem:** Tests fail with Firebase initialization errors

**Solution:**
Mocking is configured in `conftest.py`. If still failing:
```python
# In conftest.py, ensure mocks are properly set up
@pytest.fixture(scope="session", autouse=True)
def mock_firebase():
    with patch('firebase_admin.initialize_app'):
        yield
```

#### 3. Slow Tests

**Problem:** Tests take too long

**Solution:**
```bash
# Run only fast unit tests
pytest -m unit

# Or run in parallel
pytest -n auto
```

#### 4. Asyncio Errors

**Problem:** `RuntimeError: Event loop is closed`

**Solution:**
Make sure `pytest-asyncio` is installed and tests are marked:
```python
@pytest.mark.asyncio
async def test_async():
    ...
```

#### 5. Coverage Not Showing

**Problem:** Coverage report shows 0%

**Solution:**
```bash
# Install coverage
pip install pytest-cov

# Run with coverage
pytest --cov=.
```

### Debug Mode

Run tests with full output:
```bash
pytest -vv -s
```

- `-vv`: Very verbose
- `-s`: Don't capture stdout (shows print statements)

### Check Test Discovery

See what tests pytest finds:
```bash
pytest --collect-only
```

---

## 📝 Test Writing Best Practices

### 1. Follow AAA Pattern

```python
def test_something():
    # Arrange - Set up test data
    user = {"name": "John", "age": 30}

    # Act - Perform the action
    result = process_user(user)

    # Assert - Verify the result
    assert result['status'] == 'processed'
```

### 2. One Assert Per Test (When Possible)

```python
# ❌ Bad - Multiple unrelated asserts
def test_user():
    assert user.name == "John"
    assert user.age == 30
    assert user.email == "john@example.com"

# ✅ Good - Focused tests
def test_user_name():
    assert user.name == "John"

def test_user_age():
    assert user.age == 30
```

### 3. Descriptive Test Names

```python
# ❌ Bad
def test_1():
    ...

# ✅ Good
def test_login_with_valid_credentials_succeeds():
    ...

def test_login_with_invalid_password_returns_error():
    ...
```

### 4. Use Fixtures for Reusable Setup

```python
@pytest.fixture
def sample_user():
    return {"name": "Test User", "email": "test@example.com"}

def test_user_creation(sample_user):
    user = create_user(sample_user)
    assert user.name == "Test User"
```

### 5. Mark Tests Appropriately

```python
@pytest.mark.unit  # Fast, isolated
@pytest.mark.integration  # May use external services
@pytest.mark.slow  # Takes >1 second
@pytest.mark.security  # Security-related
```

---

## 🎯 Coverage Targets by Module

| Module | Target | Priority |
|--------|--------|----------|
| `security.py` | 95%+ | Critical |
| `functions.py` | 90%+ | High |
| `routers/login.py` | 90%+ | High |
| `routers/signup.py` | 90%+ | High |
| `routers/admin.py` | 85%+ | High |
| `app.py` | 80%+ | Medium |
| `middleware.py` | 85%+ | Medium |
| `logging_config.py` | 70%+ | Medium |

---

## 📚 Additional Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Pytest Best Practices](https://docs.pytest.org/en/latest/goodpractices.html)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [Coverage.py Documentation](https://coverage.readthedocs.io/)

---

## 🔍 Quick Reference

### Essential Commands

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov

# Run fast tests only
pytest -m unit

# Run and stop on first failure
pytest -x

# Run last failed tests
pytest --lf

# Run in parallel
pytest -n auto

# Generate HTML coverage report
pytest --cov=. --cov-report=html

# Run specific test
pytest tests/test_security.py::TestCSRFProtection::test_generate_csrf_token
```

### Test Markers

- `@pytest.mark.unit` - Fast unit tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.security` - Security tests
- `@pytest.mark.auth` - Authentication tests
- `@pytest.mark.slow` - Slow-running tests
- `@pytest.mark.asyncio` - Async tests

---

## 📊 Current Test Statistics

Run this to see current stats:
```bash
pytest --collect-only | grep "test session starts"
```

**Target:** 100+ tests across all categories
**Current Status:** Check with command above

---

## ✅ Testing Checklist for New Features

When adding new features:

- [ ] Write unit tests for new functions
- [ ] Write integration tests for new endpoints
- [ ] Add security tests if handling user input
- [ ] Update fixtures if needed
- [ ] Run full test suite: `pytest`
- [ ] Check coverage: `pytest --cov`
- [ ] Ensure coverage doesn't drop below 70%
- [ ] Mark tests with appropriate markers
- [ ] Add docstrings to test functions

---

Need help? Check the [troubleshooting section](#troubleshooting) or create an issue.
