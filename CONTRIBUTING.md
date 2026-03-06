# Contributing to ai-pr-review

Thank you for your interest in contributing to ai-pr-review! This document provides guidelines and instructions for contributing.

## Table of Contents

- [Development Setup](#development-setup)
- [Running Tests](#running-tests)
- [Code Style](#code-style)
- [Architecture](#architecture)
- [Pull Request Process](#pull-request-process)
- [Testing Your Changes](#testing-your-changes)

## Development Setup

### Prerequisites

- Python 3.8 or higher
- Git
- A GitHub account
- An OpenAI-compatible API key (for testing)

### Local Setup

1. **Fork and clone the repository:**
   ```bash
   git clone https://github.com/YOUR_USERNAME/ai-pr-review.git
   cd ai-pr-review
   ```

2. **No dependencies required:**
   This project uses only Python standard library modules. No `pip install` needed!

3. **Verify setup:**
   ```bash
   python3 test.py
   ```
   All tests should pass.

## Running Tests

### Run All Tests

```bash
python3 test.py
```

Expected output:
```
Running ai-pr-review smoke tests...

test_plain_base_url ... ok
test_already_has_completions_path ... ok
...
----------------------------------------------------------------------
Ran 39 tests in 0.002s

OK
```

### Run Specific Test Class

```bash
python3 -m unittest test.TestFindingsParser
```

### Run Specific Test

```bash
python3 -m unittest test.TestFindingsParser.test_parse_simple_file_line
```

### Test Coverage

The test suite includes:

- **Unit tests**: Test individual functions in isolation
- **Integration tests**: Test how components work together
- **Smoke tests**: Basic functionality checks

Current test coverage:
- 39 tests total
- Covers parsing, comparison, debounce logic, and API helper signatures

## Code Style

### Python Style Guide

We follow [PEP 8](https://pep8.org/) with a few specifics:

**Formatting:**
- Use 4 spaces for indentation (no tabs)
- Maximum line length: 100 characters
- Use blank lines to separate logical sections

**Imports:**
```python
# Standard library first
import json
import os

# Third-party next
from datetime import datetime

# Local imports last
from review import Finding
```

**Naming conventions:**
- Functions: `snake_case` (e.g., `parse_findings`)
- Classes: `PascalCase` (e.g., `TestFindingsParser`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `MAX_DIFF_CHARS`)
- Variables: `snake_case` (e.g., `review_text`)

**Comments:**
- Use section headers with `──` delimiters:
  ```python
  # ── Findings Parser ────────────────────────────────────────────────────────
  ```
- Write docstrings for all public functions:
  ```python
  def parse_findings(review_text: str) -> List[Finding]:
      """
      Parse findings from AI review text.
      
      Args:
          review_text: The review text to parse
      
      Returns:
          List of Finding objects
      """
  ```

**Type hints:**
- Use type hints for function signatures:
  ```python
  def gh_get(url: str, gh_token: str, retries: int = 3) -> Union[dict, list]:
  ```

**No external dependencies:**
- This project intentionally uses only Python standard library
- Do not add requirements.txt or external packages
- Keep it simple and dependency-free

## Architecture

### Key Design Principles

1. **No Dependencies**: Uses only Python standard library
2. **Single File**: Core logic in `review.py` (~700 lines)
3. **Modular Functions**: Helper functions for GitHub API, parsing, etc.
4. **Explicit Parameters**: No global state (recently refactored)

### Module Structure

```
ai-pr-review/
├── review.py          # Main action logic (~700 lines)
├── test.py            # Test suite (~400 lines)
├── action.yml         # GitHub Action definition
├── README.md          # User documentation
└── CONTRIBUTING.md    # This file
```

### Code Organization in review.py

```python
# 1. Imports
# 2. Data Classes (Finding)
# 3. Parsing Functions (parse_findings, extract_file_and_line, compare_findings)
# 4. GitHub API Helpers (gh_get, gh_post, gh_patch, gh_list_review_comments)
# 5. Comment Helpers (has_existing_comment, findings_to_review_comments)
# 6. Main Function (environment setup, API calls, posting)
```

### Key Functions

**Parsing:**
- `parse_findings()` - Extracts findings from AI review text
- `extract_file_and_line()` - Parses file:line references
- `compare_findings()` - Compares old vs new findings

**GitHub API:**
- `gh_get()` - GET request to GitHub API
- `gh_post()` - POST request to GitHub API
- `gh_patch()` - PATCH request to GitHub API
- `gh_list_review_comments()` - Fetch existing review comments

**Comment Management:**
- `has_existing_comment()` - Duplicate detection
- `findings_to_review_comments()` - Convert findings to review format
- `mark_findings_resolved()` - Mark resolved findings with strikethrough

### Important: Module-Level Code Execution

**All module-level execution has been moved into `main()`.**

This is critical for testability:
- ✅ Tests can import `review.py` without executing code
- ✅ No environment setup needed before importing
- ✅ Functions are testable in isolation

**Do NOT add module-level code outside of functions.**

## Pull Request Process

### Before Submitting

1. **Run tests:**
   ```bash
   python3 test.py
   ```
   All tests must pass.

2. **Check syntax:**
   ```bash
   python3 -m py_compile review.py test.py
   ```

3. **Update documentation:**
   - Update README.md if you change user-facing features
   - Update action.yml if you add/change inputs
   - Update tests for new functionality

4. **Test manually:**
   - Create a test PR
   - Trigger the action with `/ai-review`
   - Verify the review posts correctly

### PR Guidelines

**PR Title:**
- Use conventional commits format:
  - `feat: add new feature`
  - `fix: resolve bug in parsing`
  - `refactor: improve code structure`
  - `docs: update documentation`
  - `test: add tests for X`

**PR Description:**
Include:
- Summary of changes
- Why this change is needed
- How to test
- Any breaking changes

**Example:**
```markdown
## Summary
- Add multi-line comment support for findings
- Fix duplicate detection for multi-line ranges

## Test Plan
1. Create PR with multi-line code changes
2. Trigger `/ai-review`
3. Verify multi-line comments post successfully
4. Trigger again, verify no duplicates

## Breaking Changes
None - backward compatible
```

### Review Process

1. All PRs require at least one review
2. CI tests must pass
3. Address all review feedback
4. Squash commits before merging (optional)

## Testing Your Changes

### Manual Integration Testing

**Setup:**
1. Fork this repository
2. Enable GitHub Actions on your fork
3. Add your API key as a repository secret: `AI_API_KEY`

**Test scenarios:**

1. **Basic review:**
   - Create a test PR
   - Comment `/ai-review`
   - Verify review posts with findings

2. **Debounce:**
   - Trigger `/ai-review` twice within 1 minute
   - Second should skip with notice message

3. **Duplicate detection:**
   - Trigger `/ai-review` twice on same commit
   - Second should skip already-commented lines

4. **Resolved findings:**
   - Fix one of the issues
   - Trigger `/ai-review` again
   - Previous review should mark it as resolved

5. **Multi-line findings:**
   - Create PR with multi-line code changes
   - Verify multi-line comments work correctly

### Test Payload Examples

**Single-line finding:**
```
### 🔴 Critical
- src/auth.py:45 - SQL injection vulnerability
```

**Multi-line finding:**
```
### 🟡 Warning
- src/api.py:120-125 - Missing input validation
```

### Debugging

**Enable debug output:**
```yaml
- uses: your-fork/ai-pr-review@main
  with:
    api_key: ${{ secrets.AI_API_KEY }}
    # ... other inputs
  env:
    ACTIONS_STEP_DEBUG: true
```

**Common issues:**

1. **NameError: name 'gh_token' is not defined**
   - Ensure `GH_TOKEN` is set in workflow
   - Check helper functions accept `gh_token` as parameter

2. **422 Validation Failed**
   - Check file paths in findings exist in diff
   - Verify line numbers are within diff range
   - Multi-line comments need `start_side` parameter

3. **Tests fail after changes**
   - Run `python3 test.py` locally
   - Check if you added module-level code
   - Verify imports work without environment setup

## Getting Help

- Open an issue for bugs or feature requests
- Check existing issues before creating new ones
- Provide minimal reproduction steps

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing to ai-pr-review! 🎉
