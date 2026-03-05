#!/usr/bin/env python3
"""
AI PR Review — provider-agnostic code review via any OpenAI-compatible API.
Works with both pull_request and issue_comment trigger events.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

# ── Read inputs ───────────────────────────────────────────────────────────────

api_key        = os.environ.get("INPUT_API_KEY", "").strip()
base_url       = os.environ.get("INPUT_BASE_URL", "").strip().rstrip("/")
model          = os.environ.get("INPUT_MODEL", "").strip()
system_prompt  = os.environ.get("INPUT_SYSTEM_PROMPT", "").strip()
max_tokens     = int(os.environ.get("INPUT_MAX_TOKENS", "2048"))
max_diff_chars = int(os.environ.get("INPUT_MAX_DIFF_CHARS", "80000"))
post_mode      = os.environ.get("INPUT_POST_MODE", "comment").strip().lower()
language       = os.environ.get("INPUT_LANGUAGE", "english").strip()
trigger_phrase = os.environ.get("INPUT_TRIGGER_PHRASE", "/ai-review").strip()
debounce_minutes = int(os.environ.get("INPUT_DEBOUNCE_MINUTES", "1"))
event_name     = os.environ.get("EVENT_NAME", "").strip()
comment_body   = os.environ.get("COMMENT_BODY", "").strip()
gh_token       = os.environ.get("GH_TOKEN", "").strip()
gh_repo        = os.environ.get("GH_REPO", "").strip()
gh_pr_number   = os.environ.get("GH_PR_NUMBER", "").strip()
gh_sha         = os.environ.get("GH_SHA", "").strip()

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
if post_mode not in ("comment", "review"):
    errors.append(f"post_mode must be 'comment' or 'review', got '{post_mode}'")

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
    def gh_get(url: str) -> dict:
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {gh_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:500]
            print(f"::warning::Failed to check recent reviews: HTTP {e.code}")
            return {}
        except urllib.error.URLError as e:
            print(f"::warning::Failed to check recent reviews: {e.reason}")
            return {}

    try:
        comments_url = f"https://api.github.com/repos/{gh_repo}/issues/{gh_pr_number}/comments"
        comments_data = gh_get(comments_url)
        
        if isinstance(comments_data, list):
            cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=debounce_minutes)
            
            for comment in comments_data:
                user_login = comment.get("user", {}).get("login", "")
                comment_body_text = comment.get("body", "")
                created_at_str = comment.get("created_at", "")
                
                if user_login == "github-actions[bot]" and "## 🤖 AI Code Review" in comment_body_text:
                    try:
                        created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                        if created_at > cutoff_time:
                            print(
                                f"::notice::Recent AI review found ({created_at_str}). "
                                f"Skipping to prevent duplicate (debounce: {debounce_minutes}m)."
                            )
                            sys.exit(0)
                    except (ValueError, TypeError):
                        continue
    except Exception as e:
        print(f"::warning::Debounce check failed: {e}. Proceeding with review.")

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

# ── Post to GitHub ────────────────────────────────────────────────────────────

review_comment_body = (
    f"## 🤖 AI Code Review\n\n"
    f"{review_text}\n\n"
    f"---\n"
    f"*Model: `{model}` · [ai-pr-review](https://github.com/hilleer/ai-pr-review)*"
)

def gh_post(url: str, payload: dict, retries: int = 3) -> dict:
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

base_gh = f"https://api.github.com/repos/{gh_repo}"

if post_mode == "review":
    gh_post(
        f"{base_gh}/pulls/{gh_pr_number}/reviews",
        {"commit_id": gh_sha, "body": review_comment_body, "event": "COMMENT"},
    )
    print("Review posted to PR Reviews tab.")
else:
    gh_post(
        f"{base_gh}/issues/{gh_pr_number}/comments",
        {"body": review_comment_body},
    )
    print("Review posted as PR comment.")

# ── Set action outputs ────────────────────────────────────────────────────────

github_output = os.environ.get("GITHUB_OUTPUT", "")
if github_output:
    with open(github_output, "a") as f:
        preview = review_text[:1000].replace("\n", "%0A").replace("\r", "")
        f.write(f"review_body={preview}\n")
        f.write(f"model_used={model}\n")

print("✅ Done.")
