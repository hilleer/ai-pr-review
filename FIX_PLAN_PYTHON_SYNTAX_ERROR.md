# Fix Plan: Python Syntax Error in action.yml

## Problem

The workflow fails with a Python syntax error:

```
SyntaxError: invalid syntax
File "/home/runner/work/_temp/...", line 1
    /home/runner/work/_actions/hilleer/ai-pr-review/v1/review.py
    ^
```

## Root Cause

In `action.yml` line 195-212, the step configuration is incorrect:

```yaml
- name: Run AI review
  id: run_review
  shell: python3 {0}  # ❌ WRONG: This tries to execute the file path as Python code
  run: ${{ github.action_path }}/review.py
```

When `shell: python3 {0}` is used, GitHub Actions passes the content of `run` directly to Python. Since `run` contains a file path, Python tries to execute the path as code, resulting in a syntax error.

## Solution

Change the step to use bash shell and execute the Python script with `python3`:

### File: `/home/dah/code/ai-pr-review/action.yml`

**Lines 193-212:**

**BEFORE (broken):**
```yaml
- name: Run AI review
  id: run_review
  shell: python3 {0}
  env:
    INPUT_API_KEY: ${{ inputs.api_key }}
    INPUT_BASE_URL: ${{ inputs.base_url }}
    INPUT_MODEL: ${{ inputs.model }}
    INPUT_SYSTEM_PROMPT: ${{ inputs.system_prompt }}
    INPUT_MAX_TOKENS: ${{ inputs.max_tokens }}
    INPUT_MAX_DIFF_CHARS: ${{ inputs.max_diff_chars }}
    INPUT_POST_MODE: ${{ inputs.post_mode }}
    INPUT_LANGUAGE: ${{ inputs.language }}
    INPUT_TRIGGER_PHRASE: ${{ inputs.trigger_phrase }}
    EVENT_NAME: ${{ github.event_name }}
    COMMENT_BODY: ${{ github.event.comment.body }}
    GH_TOKEN: ${{ inputs.github_token }}
    GH_REPO: ${{ github.repository }}
    GH_PR_NUMBER: ${{ steps.pr_context.outputs.pr_number }}
    GH_SHA: ${{ steps.pr_context.outputs.head_sha }}
  run: ${{ github.action_path }}/review.py
```

**AFTER (fixed):**
```yaml
- name: Run AI review
  id: run_review
  shell: bash
  env:
    INPUT_API_KEY: ${{ inputs.api_key }}
    INPUT_BASE_URL: ${{ inputs.base_url }}
    INPUT_MODEL: ${{ inputs.model }}
    INPUT_SYSTEM_PROMPT: ${{ inputs.system_prompt }}
    INPUT_MAX_TOKENS: ${{ inputs.max_tokens }}
    INPUT_MAX_DIFF_CHARS: ${{ inputs.max_diff_chars }}
    INPUT_POST_MODE: ${{ inputs.post_mode }}
    INPUT_LANGUAGE: ${{ inputs.language }}
    INPUT_TRIGGER_PHRASE: ${{ inputs.trigger_phrase }}
    EVENT_NAME: ${{ github.event_name }}
    COMMENT_BODY: ${{ github.event.comment.body }}
    GH_TOKEN: ${{ inputs.github_token }}
    GH_REPO: ${{ github.repository }}
    GH_PR_NUMBER: ${{ steps.pr_context.outputs.pr_number }}
    GH_SHA: ${{ steps.pr_context.outputs.head_sha }}
  run: python3 ${{ github.action_path }}/review.py
```

**Key Changes:**
1. Line 195: Change `shell: python3 {0}` to `shell: bash`
2. Line 212: Change `run: ${{ github.action_path }}/review.py` to `run: python3 ${{ github.action_path }}/review.py`

## Implementation Steps

1. Edit `/home/dah/code/ai-pr-review/action.yml`
2. Apply the changes shown above (lines 195 and 212)
3. Commit the fix:
   ```bash
   cd /home/dah/code/ai-pr-review
   git add action.yml
   git commit -m "fix: use bash shell to execute Python script instead of python3 shell"
   git push origin main
   ```
4. The fix will be automatically available since the action is referenced as `hilleer/ai-pr-review@v1`

## Verification

After pushing the fix:
1. Go to: https://github.com/hilleer/minask/pull/1
2. Comment: `/ai-review`
3. Verify the workflow runs successfully:
   - ✅ "Run AI review" step completes without syntax error
   - ✅ AI review is posted as a PR comment

## Why This Works

Using `shell: bash` with `run: python3 script.py`:
1. GitHub Actions starts a bash shell
2. Bash executes the command: `python3 /path/to/review.py`
3. Python runs the script file (correct)

Using `shell: python3 {0}` with `run: /path/to/script.py`:
1. GitHub Actions passes the file path to Python's stdin
2. Python tries to parse "/path/to/script.py" as code (incorrect)
3. Syntax error occurs because a file path is not valid Python code

## Testing

To test locally before committing:
```bash
# This works (correct approach):
python3 /home/dah/code/ai-pr-review/review.py

# This fails (what the broken action was doing):
echo "/home/dah/code/ai-pr-review/review.py" | python3
```

## Related Files

- Action definition: `/home/dah/code/ai-pr-review/action.yml`
- Python script: `/home/dah/code/ai-pr-review/review.py`
- Workflow using action: `/home/dah/code/minask/.github/workflows/ai-pr-review.yml`

## Status

- [x] Root cause identified
- [ ] Fix applied to action.yml
- [ ] Fix committed and pushed
- [ ] Tested on PR #1
- [ ] Confirmed working

---

**Assignee:** Agent colleague
**Priority:** High (blocks AI PR review functionality)
**Estimated time:** 2 minutes to apply fix
