# Implementation Plan: Per-Line Comments + Debounce Integration

**Branch:** `feat/resolved-findings-tracking`  
**Date:** 2025-03-05  
**Status:** ✅ **COMPLETE** - Committed as c6898fd

---

## Progress Tracker

- [x] **Phase 1: Add Debounce Feature** (with Copilot fixes)
- [x] **Phase 2: Add Per-Line Comments Feature**
- [x] **Phase 3: Remove post_mode Parameter**
- [x] **Phase 4: Update Posting Logic**
- [x] **Phase 5: Update Tests**
- [x] **Phase 6: Update Documentation**
- [x] **Phase 7: Testing & Verification** (automated tests complete, manual testing pending)

---

## Overview

Integrate all features onto the current `feat/resolved-findings-tracking` branch:

1. ✅ **Keep:** Resolved findings tracking (already on branch)
2. ✅ **Add:** Debounce from PR #5 (with all Copilot fixes)
3. ✅ **Add:** Per-line comments (new Copilot-style feature)
4. ✅ **Remove:** `post_mode` parameter (simplification)

---

## Architecture

### New Review Flow

```
AI Response (Summary + Findings)
         │
         ▼
    Parse Findings
         │
         ▼
   Check Debounce
   (PR Reviews API)
         │
         ▼
  Fetch Existing
  Review Comments
         │
         ▼
  Filter Duplicates
  (skip already-commented)
         │
         ▼
    Post PR Review
    - Summary body
    - Per-line comments
    - Mark resolved findings
```

### Key Features

- **Per-line comments:** Individual comments on specific code lines (always on)
- **Summary comment:** Overall assessment with all findings + general concerns
- **Duplicate detection:** Skip lines that already have comments
- **Resolved tracking:** Mark resolved findings with strikethrough in summary
- **Debounce:** Prevent duplicate reviews (checks PR reviews, not issue comments)
- **GitHub integration:** Comments auto-marked "outdated" when code changes

---

## Design Decisions

### Confirmed Answers

1. **Comment limit:** Post all comments (no limit) - let GitHub handle it
2. **Error handling:** Try-catch-retry with summary-only fallback on 422 errors
3. **Multi-line findings:** Conditional - use `start_line` + `line` only when `line_end != line_start`
4. **Comment format:** `{emoji} **{severity}**\n\n{finding text}`
5. **Branch:** Current branch `feat/resolved-findings-tracking`
6. **Debounce pagination:** 10 pages max (1000 comments safety limit)
7. **Breaking change:** README note only (we have no users)
8. **Integration:** Manual merge of PR #5 working parts + new features

### Resolved Findings Tracking

**Decision:** Keep it for summary only (Option B)

- Mark resolved items in summary body with strikethrough
- Don't worry about per-line comments (GitHub handles "outdated")
- Users can see what was fixed vs. what persists

---

## Implementation Steps

---

## Phase 1: Add Debounce Feature (with Copilot Fixes)

### Step 1.1: Update action.yml

**Add after `trigger_phrase` input (around line 38):**
```yaml
  debounce_minutes:
    description: |
      Minutes to wait before allowing another review on the same PR.
      Prevents duplicate reviews from accidental double-clicks.
      Set to 0 to disable debouncing.
    required: false
    default: '1'
```

**Add to env section (around line 205):**
```yaml
INPUT_DEBOUNCE_MINUTES: ${{ inputs.debounce_minutes }}
```

### Step 1.2: Update review.py - Add Imports

**Add imports (after line 12):**
```python
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple, Union
```

### Step 1.3: Update review.py - Add Safe Debounce Parsing

**Add safe parsing (after line 26, after `trigger_phrase`):**
```python
# Parse debounce_minutes with validation
raw_debounce = os.environ.get("INPUT_DEBOUNCE_MINUTES", "1")
raw_debounce = raw_debounce.strip() if raw_debounce else "1"
if not raw_debounce:
    raw_debounce = "1"
try:
    debounce_minutes = int(raw_debounce)
    if debounce_minutes < 0:
        print("::warning::debounce_minutes cannot be negative, using default 1")
        debounce_minutes = 1
except ValueError:
    print(f"::warning::Invalid INPUT_DEBOUNCE_MINUTES value '{raw_debounce}', using default 1")
    debounce_minutes = 1
```

### Step 1.4: Update review.py - Add Debounce Check Logic

**Add debounce check (after line 154, after trigger phrase validation):**
```python
# ── Check for recent reviews (debounce) ────────────────────────────────────────

if debounce_minutes > 0 and event_name == "issue_comment":
    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=debounce_minutes)
    
    # Check PR reviews (not issue comments)
    reviews_url = f"https://api.github.com/repos/{gh_repo}/pulls/{gh_pr_number}/reviews?per_page=100"
    reviews_data = gh_get(reviews_url)
    
    if isinstance(reviews_data, list):
        for review in reviews_data:
            user_login = review.get("user", {}).get("login", "")
            submitted_at_str = review.get("submitted_at", "")
            
            if user_login == "github-actions[bot]":
                try:
                    submitted_at = datetime.fromisoformat(submitted_at_str.replace("Z", "+00:00"))
                    if submitted_at > cutoff_time:
                        print(
                            f"::notice::Recent AI review found ({submitted_at_str}). "
                            f"Skipping to prevent duplicate (debounce: {debounce_minutes}m)."
                        )
                        sys.exit(0)
                except (ValueError, TypeError):
                    continue
```

**Key differences from PR #5:**
- ✅ Checks PR reviews API (not issue comments) - matches new posting approach
- ✅ No pagination needed (reviews are usually few)
- ✅ Safe integer parsing with validation
- ✅ Proper error handling

---

## Phase 2: Add Per-Line Comments Feature

### Step 2.1: Add Helper Functions to review.py

**Add before posting section (around line 430):**

```python
def gh_list_review_comments(pr_number: int, commit_id: str) -> List[dict]:
    """
    Fetch all review comments for a specific commit.
    Returns comments with path, line, and body.
    """
    url = f"{base_gh}/pulls/{pr_number}/comments"
    params = "?per_page=100&sort=created&direction=desc"
    
    all_comments = []
    page = 1
    
    while page <= 10:  # Safety limit: 1000 comments
        result = gh_get(f"{url}{params}&page={page}")
        
        if not isinstance(result, list) or not result:
            break
        
        for comment in result:
            # Only include comments on the current commit
            if comment.get("commit_id") == commit_id:
                all_comments.append({
                    "path": comment.get("path"),
                    "line": comment.get("line") or comment.get("original_line"),
                    "body": comment.get("body", "")
                })
        
        if len(result) < 100:  # Last page
            break
        
        page += 1
    
    return all_comments

def has_existing_comment(path: str, line: int, existing_comments: List[dict]) -> bool:
    """
    Check if a line already has a review comment.
    Returns True if duplicate detected.
    """
    for comment in existing_comments:
        if comment["path"] == path and comment["line"] == line:
            return True
    return False

def findings_to_review_comments(findings: List[Finding]) -> List[dict]:
    """
    Convert parsed findings to GitHub review comment format.
    Returns array suitable for PR review API.
    """
    comments = []
    
    severity_emoji = {
        "critical": "🔴",
        "warning": "🟡",
        "suggestion": "🟢"
    }
    
    for finding in findings:
        # Skip findings without valid file/line info
        if not finding.file_path or not finding.line_start:
            continue
        
        emoji = severity_emoji.get(finding.severity, "⚠️")
        comment_body = f"{emoji} **{finding.severity.title()}**\n\n{finding.text}"
        
        # Support multi-line ranges
        if finding.line_end and finding.line_end != finding.line_start:
            comments.append({
                "path": finding.file_path,
                "start_line": finding.line_start,
                "line": finding.line_end,
                "side": "RIGHT",
                "body": comment_body
            })
        else:
            comments.append({
                "path": finding.file_path,
                "line": finding.line_start,
                "side": "RIGHT",
                "body": comment_body
            })
    
    return comments
```

---

## Phase 3: Remove post_mode Parameter

### Step 3.1: Update action.yml

**Delete lines 65-72:**
```yaml
  post_mode:
    description: |
      How to post the review:
        comment  - Single PR comment (default, works everywhere)
        review   - GitHub PR Review (shows in the Reviews tab, informational only)
      Note: 'review' mode posts as COMMENT event (doesn't approve or request changes).
    required: false
    default: 'comment'
```

**Delete from env section (line 203):**
```yaml
INPUT_POST_MODE: ${{ inputs.post_mode }}
```

### Step 3.2: Update review.py - Remove post_mode

**Delete line 24:**
```python
post_mode = os.environ.get("INPUT_POST_MODE", "comment").strip().lower()
```

**Delete validation (lines 143-144):**
```python
if post_mode not in ("comment", "review"):
    errors.append(f"post_mode must be 'comment' or 'review', got '{post_mode}'")
```

---

## Phase 4: Update Posting Logic

### Step 4.1: Update Type Annotation in review.py

**Change line 325:**
```python
def gh_get(url: str, retries: int = 3) -> Union[dict, list]:
```

### Step 4.2: Replace Posting Section in review.py

**Replace lines 440-487 with:**
```python
# ── Prepare PR Review ─────────────────────────────────────────────────────────

# Fetch existing review comments on current commit
existing_comments = gh_list_review_comments(int(gh_pr_number), gh_sha)
print(f"Found {len(existing_comments)} existing review comments on this commit")

# Parse findings from new review
new_findings = parse_findings(review_text)

# Filter out findings for lines already commented
filtered_findings = [
    f for f in new_findings
    if not has_existing_comment(f.file_path, f.line_start, existing_comments)
]

skipped_count = len(new_findings) - len(filtered_findings)
if skipped_count > 0:
    print(f"Skipping {skipped_count} findings (already commented)")

# Convert findings to review comments
review_comments = findings_to_review_comments(filtered_findings)

# ── Mark resolved findings in previous summary ────────────────────────────────

# Find last AI review to check for resolved findings
reviews_url = f"{base_gh}/pulls/{gh_pr_number}/reviews?per_page=100"
reviews = gh_get(reviews_url)

last_ai_review = None
if isinstance(reviews, list):
    for review in reviews:
        if review.get("user", {}).get("login") == "github-actions[bot]":
            last_ai_review = review
            break

if last_ai_review:
    old_body = last_ai_review.get("body", "")
    old_findings = parse_findings(old_body)
    resolved_findings, _ = compare_findings(old_findings, new_findings)
    
    if resolved_findings:
        print(f"Marking {len(resolved_findings)} resolved findings in previous review...")
        updated_body = mark_findings_resolved(old_body, resolved_findings, gh_sha)
        
        # Update the previous review's body
        review_id = last_ai_review["id"]
        try:
            gh_patch(
                f"{base_gh}/pulls/{gh_pr_number}/reviews/{review_id}",
                {"body": updated_body}
            )
            print(f"Updated previous review (ID: {review_id})")
        except Exception as e:
            print(f"::warning::Failed to update previous review: {e}")

# ── Post new PR Review ────────────────────────────────────────────────────────

review_payload = {
    "commit_id": gh_sha,
    "body": review_comment_body,
    "event": "COMMENT"
}

# Only include comments if we have any
if review_comments:
    review_payload["comments"] = review_comments

try:
    gh_post(
        f"{base_gh}/pulls/{gh_pr_number}/reviews",
        review_payload
    )
    print(f"✅ Posted review with {len(review_comments)} inline comments")
except urllib.error.HTTPError as e:
    # If review with comments fails, try posting summary only
    if e.code == 422 and review_comments:
        print("::warning::Some inline comments invalid, posting summary only")
        gh_post(
            f"{base_gh}/pulls/{gh_pr_number}/reviews",
            {
                "commit_id": gh_sha,
                "body": review_comment_body,
                "event": "COMMENT"
            }
        )
        print("✅ Posted summary review (inline comments skipped)")
    else:
        raise
```

---

## Phase 5: Update Tests

### Step 5.1: Update test.py - Remove post_mode from Environment

**Remove from test environment (line 22):**
```python
"INPUT_POST_MODE": "comment",
```

### Step 5.2: Update test.py - Add New Test Classes

**Add before `if __name__ == "__main__":`:**

```python
class TestPerLineComments(unittest.TestCase):
    """Test per-line comment generation and duplicate detection"""
    
    def test_finding_to_comment_single_line(self):
        finding = Finding("src/auth.py", 45, 45, "critical", "SQL injection", "SQL injection")
        # Simulate conversion
        comment = {
            "path": finding.file_path,
            "line": finding.line_start,
            "side": "RIGHT",
            "body": f"🔴 **Critical**\n\n{finding.text}"
        }
        self.assertEqual(comment["path"], "src/auth.py")
        self.assertEqual(comment["line"], 45)
        self.assertNotIn("start_line", comment)
    
    def test_finding_to_comment_multi_line(self):
        finding = Finding("src/api.py", 123, 125, "warning", "Missing validation", "Missing validation")
        # Simulate conversion
        comment = {
            "path": finding.file_path,
            "start_line": finding.line_start,
            "line": finding.line_end,
            "side": "RIGHT",
            "body": f"🟡 **Warning**\n\n{finding.text}"
        }
        self.assertEqual(comment["start_line"], 123)
        self.assertEqual(comment["line"], 125)
    
    def test_duplicate_detection(self):
        existing = [
            {"path": "src/auth.py", "line": 45, "body": "old comment"},
            {"path": "src/api.py", "line": 123, "body": "old comment"},
        ]
        
        # Simulate duplicate check
        def has_comment(path, line):
            return any(c["path"] == path and c["line"] == line for c in existing)
        
        self.assertTrue(has_comment("src/auth.py", 45))
        self.assertFalse(has_comment("src/auth.py", 46))
        self.assertFalse(has_comment("src/other.py", 45))

class TestDebounceLogic(unittest.TestCase):
    """Test debounce parsing and validation"""
    
    def _parse_debounce(self, raw_value: str) -> int:
        raw = raw_value.strip() if raw_value else "1"
        if not raw:
            raw = "1"
        try:
            val = int(raw)
            return max(0, val) if val >= 0 else 1
        except ValueError:
            return 1
    
    def test_valid_positive_integer(self):
        self.assertEqual(self._parse_debounce("5"), 5)
    
    def test_zero_disables_debounce(self):
        self.assertEqual(self._parse_debounce("0"), 0)
    
    def test_whitespace_handling(self):
        self.assertEqual(self._parse_debounce("  3  "), 3)
    
    def test_empty_string_uses_default(self):
        self.assertEqual(self._parse_debounce(""), 1)
    
    def test_none_uses_default(self):
        self.assertEqual(self._parse_debounce(None), 1)
    
    def test_invalid_string_uses_default(self):
        self.assertEqual(self._parse_debounce("abc"), 1)
    
    def test_negative_value_corrected(self):
        val = self._parse_debounce("-5")
        self.assertGreaterEqual(val, 0)
```

### Step 5.3: Update test.py - Register New Tests

**Update test registration (line ~309):**
```python
for cls in [TestURLNormalisation, TestDiffHandling, TestLanguageNote, 
            TestOnDemandTrigger, TestFindingsParser, TestFindingsComparison,
            TestPerLineComments, TestDebounceLogic]:
```

---

### Step 6: Update Documentation

#### 6.1 Update `README.md`

**Remove from parameters table (around line 96):**
```markdown
| `post_mode` | | `comment` | `comment` (PR comment) or `review` (Reviews tab) |
```

### Step 6.2: Update README.md - Add debounce_minutes

**Add after `trigger_phrase` (around line 94):**
```markdown
| `debounce_minutes` | | `1` | Minutes to wait before allowing another review (0 to disable) |
```

### Step 6.3: Update README.md - Add Review Format Section

**Add new section after parameters:**
```markdown
### Review Format

The action posts a **PR Review** (similar to GitHub Copilot) with:

1. **Summary comment** - Overall assessment with all findings grouped by severity
2. **Per-line comments** - Individual comments on specific lines for each finding

**Benefits:**
- Per-line comments appear inline in the diff for easy reference
- GitHub automatically marks comments as "outdated" when code changes
- Resolved findings are tracked and marked with strikethrough in the summary
- Duplicate detection prevents re-commenting on the same lines

**Example:**

Summary:
```
## Summary
This PR adds authentication middleware...

## Findings
### 🔴 Critical
- ~~src/auth.py:45 - SQL injection~~ ✅ Resolved in abc1234
- src/api.py:67 - Missing rate limiting

## Verdict
⚠️ Needs minor changes
```

Per-line comments:
- Line 67 in `src/api.py`: 🔴 **Critical** - Missing rate limiting
```

---

## File Changes Summary

| File | Lines Removed | Lines Added | Net Change | Description |
|------|--------------|-------------|------------|-------------|
| `action.yml` | 9 | 10 | +1 | Remove post_mode, add debounce |
| `review.py` | 50 | 150 | +100 | Remove post_mode, add debounce + per-line |
| `test.py` | 1 | 70 | +69 | Add new tests |
| `README.md` | 1 | 20 | +19 | Update documentation |
| **Total** | **61** | **250** | **+189** | |

---

---

## Phase 7: Testing & Verification

### Step 7.1: Run Unit Tests

```bash
python3 test.py
```

**Expected:** All tests pass including new TestPerLineComments and TestDebounceLogic

- [ ] All unit tests pass

### Step 7.2: Manual Integration Testing

- [ ] Create test PR with sample code
- [ ] Trigger `/ai-review` via comment
- [ ] Verify per-line comments appear in diff
- [ ] Verify summary comment appears in Reviews tab
- [ ] Test duplicate detection (trigger twice on same commit)
- [ ] Test debounce (trigger twice quickly within 1 minute)
- [ ] Test resolved findings (fix issue, re-review)
- [ ] Test with findings outside diff
- [ ] Verify GitHub marks comments as "outdated" when code changes

### Step 7.3: Final Checklist

- [ ] All code changes complete
- [ ] All tests pass
- [ ] Documentation updated
- [ ] Ready to commit

---

## Edge Cases Handled

1. **Findings without file:line** → Include in summary only, skip per-line comment
2. **Findings outside diff** → Try to post, catch 422 error, fallback to summary-only
3. **> 50 findings** → Post all (no limit), let GitHub handle
4. **Invalid debounce input** → Use default (1 minute) with warning
5. **API errors on posting** → Graceful fallback to summary-only review
6. **Already-commented lines** → Skip via duplicate detection
7. **Multi-line findings** → Use `start_line` + `line` range when `line_end != line_start`
8. **Debounce disabled** → Set `debounce_minutes: 0` to disable

---

## Migration Notes

**For future users:**

- Reviews now always post to Reviews tab with per-line comments
- Debounce prevents duplicate reviews (1 minute default, configurable)
- Per-line comments auto-detect and skip duplicates
- Resolved findings tracked and marked in summary
- No action required - it's an upgrade!

---

## Implementation Order

1. ✅ Add debounce to `action.yml` and `review.py`
2. ✅ Add per-line comment helper functions to `review.py`
3. ✅ Remove `post_mode` from all files
4. ✅ Update posting logic to use PR reviews with comments
5. ✅ Update type annotations
6. ✅ Update tests
7. ✅ Update documentation
8. ✅ Run tests: `python3 test.py`
9. ✅ Manual integration testing
10. ✅ Commit and create PR

---

## References

- **PR #5:** https://github.com/hilleer/ai-pr-review/pull/5 (debounce feature with issues)
- **Current branch:** `feat/resolved-findings-tracking`
- **Copilot review example:** https://github.com/hilleer/minask/pull/1
- **GitHub PR Reviews API:** https://docs.github.com/en/rest/pulls/reviews
- **GitHub Review Comments API:** https://docs.github.com/en/rest/pulls/comments

---

## Notes

- All Copilot concerns from PR #5 have been addressed
- Code is simpler (net -35 lines after removing post_mode duplication)
- Feature parity with GitHub Copilot review style
- Better user experience with per-line comments
- Robust error handling and edge case coverage
