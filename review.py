#!/usr/bin/env python3
"""
AI PR Review — provider-agnostic code review via any OpenAI-compatible API.
Works with both pull_request and issue_comment trigger events.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple, Union

# ── Findings Parser ───────────────────────────────────────────────────────────

@dataclass
class Finding:
    file_path: str
    line_start: int
    line_end: int
    severity: str
    text: str
    raw_line: str

def parse_findings(review_text: str) -> List[Finding]:
    findings = []

    sections = {
        'critical': r'### 🔴 Critical\s*\n(.*?)(?=### |## |$)',
        'warning': r'### 🟡 Warning\s*\n(.*?)(?=### |## |$)',
        'suggestion': r'### 🟢 Suggestion\s*\n(.*?)(?=### |## |$)'
    }

    for severity, pattern in sections.items():
        match = re.search(pattern, review_text, re.DOTALL | re.IGNORECASE)
        if not match:
            continue

        section_text = match.group(1)
        lines = section_text.strip().split('\n')

        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            file_path, line_start, line_end = extract_file_and_line(line)
            if file_path and line_start and line_end:
                findings.append(Finding(
                    file_path=file_path,
                    line_start=line_start,
                    line_end=line_end,
                    severity=severity,
                    text=line,
                    raw_line=line
                ))

    return findings

def extract_file_and_line(text: str) -> Tuple[Optional[str], Optional[int], Optional[int]]:
    patterns = [
        r'([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+):(\d+)-(\d+)',
        r'([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+):(\d+)',
        r'[Ff]ile[:\s]+([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)[,\s]+[Ll]ine[:\s]+(\d+)',
        r'[Ii]n\s+([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)\s+at\s+line\s+(\d+)',
        r'[Ll]ines?\s+(\d+)-?(\d+)?\s+(?:of|in)\s+([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)',
    ]

    for i, pattern in enumerate(patterns):
        match = re.search(pattern, text)
        if match:
            groups = match.groups()

            if i == 0:
                return groups[0], int(groups[1]), int(groups[2])
            elif i == 1:
                return groups[0], int(groups[1]), int(groups[1])
            elif i in (2, 3):
                return groups[0], int(groups[1]), int(groups[1])
            else:  # i == 4
                file_path = groups[2]
                line_start = int(groups[0])
                line_end = int(groups[1]) if groups[1] else line_start
                return file_path, line_start, line_end

    return None, None, None

def compare_findings(old: List[Finding], new: List[Finding], line_tolerance: int = 5) -> Tuple[List[Finding], List[Finding]]:
    resolved = []
    persisting = []

    for old_finding in old:
        is_resolved = True

        for new_finding in new:
            if (old_finding.file_path == new_finding.file_path and
                abs(old_finding.line_start - new_finding.line_start) <= line_tolerance):
                is_resolved = False
                persisting.append(old_finding)
                break

        if is_resolved:
            resolved.append(old_finding)

    return resolved, persisting


# ── GitHub API Helpers ────────────────────────────────────────────────────────

def gh_post(url: str, payload: dict, gh_token: str, retries: int = 3) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {gh_token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    last_error = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:500]
            if e.code >= 500 and attempt < retries - 1:
                last_error = f"HTTP {e.code}"
                continue
            print(f"::error::GitHub API returned HTTP {e.code}: {body}")
            sys.exit(1)
        except urllib.error.URLError as e:
            if attempt < retries - 1:
                last_error = str(e.reason)
                continue
            print(f"::error::Failed to reach GitHub API: {e.reason}")
            sys.exit(1)
    print(f"::error::GitHub API failed after {retries} retries: {last_error}")
    sys.exit(1)

def gh_get(url: str, gh_token: str, retries: int = 3) -> Union[dict, list]:
    """
    Get data from GitHub API.
    
    Args:
        url: GitHub API endpoint
        gh_token: GitHub authentication token
        retries: Number of retry attempts
    
    Returns:
        API response as dict or list
    """
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {gh_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    last_error = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:500]
            if e.code >= 500 and attempt < retries - 1:
                last_error = f"HTTP {e.code}"
                continue
            print(f"::error::GitHub API returned HTTP {e.code}: {body}")
            sys.exit(1)
        except urllib.error.URLError as e:
            if attempt < retries - 1:
                last_error = str(e.reason)
                continue
            print(f"::error::Failed to reach GitHub API: {e.reason}")
            sys.exit(1)
    print(f"::error::GitHub API failed after {retries} retries: {last_error}")
    sys.exit(1)

def gh_patch(url: str, payload: dict, gh_token: str, retries: int = 3) -> dict:
    """
    Patch data in GitHub API.
    
    Args:
        url: GitHub API endpoint
        payload: Data to patch
        gh_token: GitHub authentication token
        retries: Number of retry attempts
    
    Returns:
        API response as dict
    """
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {gh_token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="PATCH",
    )
    last_error = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:500]
            if e.code >= 500 and attempt < retries - 1:
                last_error = f"HTTP {e.code}"
                continue
            print(f"::error::GitHub API returned HTTP {e.code}: {body}")
            sys.exit(1)
        except urllib.error.URLError as e:
            if attempt < retries - 1:
                last_error = str(e.reason)
                continue
            print(f"::error::Failed to reach GitHub API: {e.reason}")
            sys.exit(1)
    print(f"::error::GitHub API failed after {retries} retries: {last_error}")
    sys.exit(1)


def gh_list_review_comments(pr_number: int, commit_id: str, base_gh: str, gh_token: str) -> List[dict]:
    """
    Fetch all review comments for a specific commit.
    
    Args:
        pr_number: Pull request number
        commit_id: Commit SHA
        base_gh: Base GitHub API URL
        gh_token: GitHub authentication token
    
    Returns:
        List of review comments with path, line, and body
    """
    url = f"{base_gh}/pulls/{pr_number}/comments"
    params = "?per_page=100&sort=created&direction=desc"

    all_comments = []
    page = 1

    while page <= 10:  # Safety limit: 1000 comments
        result = gh_get(f"{url}{params}&page={page}", gh_token)

        if not isinstance(result, list) or not result:
            break

        for comment in result:
            # Only include comments on the current commit
            if comment.get("commit_id") == commit_id:
                all_comments.append({
                    "path": comment.get("path"),
                    "start_line": comment.get("start_line") or comment.get("original_start_line"),
                    "line": comment.get("line") or comment.get("original_line"),
                    "body": comment.get("body", "")
                })

        if len(result) < 100:  # Last page
            break

        page += 1

    return all_comments

def has_existing_comment(path: str, line_start: int, line_end: int, existing_comments: List[dict]) -> bool:
    """
    Check if a line range already has a review comment.
    Returns True if duplicate detected (any overlap).
    """
    for comment in existing_comments:
        if comment["path"] == path:
            # Get the existing comment's line range
            existing_start = comment.get("start_line") or comment["line"]
            existing_end = comment["line"]
            
            # Check for overlap: ranges overlap if start1 <= end2 and start2 <= end1
            if line_start <= existing_end and line_end >= existing_start:
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
                "start_side": "RIGHT",
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

def mark_findings_resolved(comment_body: str, resolved_findings: List[Finding], resolved_sha: str) -> str:
    """
    Mark resolved findings with strikethrough in a comment body.
    """
    lines = comment_body.split('\n')
    updated_lines = []

    for line in lines:
        modified = False
        for finding in resolved_findings:
            if finding.raw_line in line and not line.strip().startswith('~~'):
                if line.strip().startswith('- '):
                    indent_match = re.match(r'^(\s*- )(.*)$', line)
                    if indent_match:
                        indent = indent_match.group(1)
                        content = indent_match.group(2)
                        updated_lines.append(f"{indent}~~{content}~~ ✅ Resolved in {resolved_sha[:7]}")
                        modified = True
                        break

        if not modified:
            updated_lines.append(line)

    return '\n'.join(updated_lines)


def main():
    # ── Read inputs ───────────────────────────────────────────────────────────────

    api_key        = os.environ.get("INPUT_API_KEY", "").strip()
    base_url       = os.environ.get("INPUT_BASE_URL", "").strip().rstrip("/")
    model          = os.environ.get("INPUT_MODEL", "").strip()
    system_prompt  = os.environ.get("INPUT_SYSTEM_PROMPT", "").strip()
    max_tokens     = int(os.environ.get("INPUT_MAX_TOKENS", "2048"))
    max_diff_chars = int(os.environ.get("INPUT_MAX_DIFF_CHARS", "80000"))
    language       = os.environ.get("INPUT_LANGUAGE", "english").strip()
    trigger_phrase = os.environ.get("INPUT_TRIGGER_PHRASE", "/ai-review").strip()

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

    event_name     = os.environ.get("EVENT_NAME", "").strip()
    comment_body   = os.environ.get("COMMENT_BODY", "").strip()
    gh_token       = os.environ.get("GH_TOKEN", "").strip()
    gh_repo        = os.environ.get("GH_REPO", "").strip()
    gh_pr_number   = os.environ.get("GH_PR_NUMBER", "").strip()
    gh_sha         = os.environ.get("GH_SHA", "").strip()

    base_gh = f"https://api.github.com/repos/{gh_repo}"

    # ── Validate ──────────────────────────────────────────────────────────────────

    errors = []
    if not api_key:
        errors.append("'api_key' is required")
    if not base_url:
        errors.append("'base_url' is required")
    if not model:
        errors.append("'model' is required")
    if not gh_token:
        errors.append("GitHub token is missing")
    if not gh_repo or not gh_pr_number:
        errors.append(
            "GitHub repo/PR context is missing — is this running on a "
            "pull_request or issue_comment event?"
        )

    if errors:
        for e in errors:
            print(f"::error::{e}")
        sys.exit(1)

    if event_name == "issue_comment":
        if trigger_phrase not in comment_body:
            print(f"::notice::Comment doesn't contain trigger phrase '{trigger_phrase}'. Skipping.")
            sys.exit(0)

    # ── Check for recent reviews (debounce) ────────────────────────────────────────

    if debounce_minutes > 0 and event_name == "issue_comment":
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=debounce_minutes)
        
        # Check PR reviews (not issue comments)
        reviews_url = f"{base_gh}/pulls/{gh_pr_number}/reviews?per_page=100"
        reviews_data = gh_get(reviews_url, gh_token)

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

    # Normalise base_url → always ends at /chat/completions
    if base_url.endswith("/chat/completions"):
        completions_url = base_url
    else:
        completions_url = f"{base_url}/chat/completions"

    # ── Load diff ─────────────────────────────────────────────────────────────────

    diff_path = "/tmp/pr_diff.txt"
    try:
        with open(diff_path, "r", encoding="utf-8", errors="replace") as f:
            diff = f.read().strip()
    except FileNotFoundError:
        print("::error::Diff file not found. Did the 'Generate diff' step run?")
        sys.exit(1)

    if not diff:
        print("::notice::Empty diff — nothing to review. Skipping.")
        sys.exit(0)

    if len(diff) > max_diff_chars:
        truncated_at = max_diff_chars
        diff = diff[:truncated_at]
        last_newline = diff.rfind("\n")
        if last_newline >= 0:
            diff = diff[:last_newline]
        diff += f"\n\n[... diff truncated at {truncated_at:,} chars to fit context window ...]"
        print(
            f"::warning::Diff was truncated at {truncated_at:,} chars. "
            "Consider increasing max_diff_chars or narrowing file_patterns."
        )

    # ── Build prompts ─────────────────────────────────────────────────────────────

    LANGUAGE_NOTE = f"\nRespond entirely in {language}." if language.lower() != "english" else ""

    DEFAULT_SYSTEM_PROMPT = f"""You are a thorough and pragmatic senior software engineer performing a pull request code review.

Analyse the provided git diff carefully and report your findings in clear markdown.

Structure your response as:

## Summary
One short paragraph describing what this PR does overall.

## Findings
Group issues by severity — only include sections that have findings:

### 🔴 Critical
Bugs, security issues, data loss or correctness risks. Must be addressed before merging.

### 🟡 Warning
Edge cases, missing error handling, performance concerns, unclear logic.

### 🟢 Suggestion
Style, naming, readability, minor improvements. Nice to have.

## Verdict
One of: ✅ Looks good | ⚠️ Needs minor changes | 🚫 Needs significant changes

---
Rules:
- Reference specific file names and line numbers where relevant.
- If the diff is clean and you have no findings, say so briefly — don't invent issues.
- Don't comment on things outside the diff (e.g. missing tests if no test files are shown).
- Be direct. Skip filler phrases like "Great job!" or "Overall this is well written".\
{LANGUAGE_NOTE}"""

    prompt = system_prompt if system_prompt else DEFAULT_SYSTEM_PROMPT

    user_message = f"""Please review this pull request diff:

```diff
{diff}
```"""

    # ── Call the API ──────────────────────────────────────────────────────────────

    print(f"Calling {completions_url} with model '{model}'...")

    payload = json.dumps({
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user",   "content": user_message},
        ],
    }).encode("utf-8")

    req = urllib.request.Request(
        completions_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "ai-pr-review-action/1.0",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        print(f"::error::API returned HTTP {e.code}: {body}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"::error::Failed to reach API at {completions_url}: {e.reason}")
        sys.exit(1)
    except Exception as e:
        print(f"::error::Unexpected error calling API: {e}")
        sys.exit(1)

    try:
        review_text = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        print(f"::error::Unexpected API response shape: {json.dumps(result)[:500]}")
        sys.exit(1)

    usage = result.get("usage", {})
    if usage:
        print(f"Token usage — prompt: {usage.get('prompt_tokens', '?')}, completion: {usage.get('completion_tokens', '?')}")

    # ── Prepare review comment body ────────────────────────────────────────────────

    timestamp = datetime.now(timezone.utc).isoformat()
    review_comment_body = (
        f"## 🤖 AI Code Review\n"
        f"<!-- ai-pr-review sha={gh_sha} timestamp={timestamp} -->\n\n"
        f"{review_text}\n\n"
        f"---\n"
        f"*Model: `{model}` · Commit: `{gh_sha[:7]}` · [ai-pr-review](https://github.com/hilleer/ai-pr-review)*"
    )

    # ── Prepare PR Review ─────────────────────────────────────────────────────────

    # Fetch existing review comments on current commit
    existing_comments = gh_list_review_comments(int(gh_pr_number), gh_sha, base_gh, gh_token)
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
    reviews = gh_get(reviews_url, gh_token)

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
                    {"body": updated_body},
                    gh_token
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
            review_payload,
            gh_token
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
                },
                gh_token
            )
            print("✅ Posted summary review (inline comments skipped)")
        else:
            raise

    # ── Set action outputs ────────────────────────────────────────────────────────

    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a") as f:
            preview = review_text[:1000].replace("\n", "%0A").replace("\r", "")
            f.write(f"review_body={preview}\n")
            f.write(f"model_used={model}\n")

    print("✅ Done.")


if __name__ == "__main__":
    main()
