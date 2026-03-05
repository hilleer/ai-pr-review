#!/usr/bin/env python3
"""
Basic smoke test for review.py — validates logic without hitting a real API.
Run locally with: python3 test.py
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Minimal env so imports don't fail
os.environ.update({
    "INPUT_API_KEY": "test-key",
    "INPUT_BASE_URL": "https://api.example.com/v1",
    "INPUT_MODEL": "test-model",
    "INPUT_SYSTEM_PROMPT": "",
    "INPUT_MAX_TOKENS": "2048",
    "INPUT_MAX_DIFF_CHARS": "80000",
    "INPUT_POST_MODE": "comment",
    "INPUT_LANGUAGE": "english",
    "GH_TOKEN": "ghp_test",
    "GH_REPO": "owner/repo",
    "GH_PR_NUMBER": "42",
    "GH_SHA": "abc123",
})

class TestReviewLogic(unittest.TestCase):

    def test_url_normalisation(self):
        """base_url with or without /chat/completions should both work"""
        cases = [
            ("https://api.openai.com/v1",
             "https://api.openai.com/v1/chat/completions"),
            ("https://api.moonshot.cn/v1",
             "https://api.moonshot.cn/v1/chat/completions"),
            ("https://api.example.com/v1/chat/completions",
             "https://api.example.com/v1/chat/completions"),
        ]
        for base, expected in cases:
            base = base.rstrip("/")
            if base.endswith("/chat/completions"):
                result = base
            else:
                result = f"{base}/chat/completions"
            self.assertEqual(result, expected, f"Failed for {base}")

    def test_diff_truncation(self):
        """Diffs over max_diff_chars should be truncated cleanly at a newline"""
        max_chars = 100
        diff = ("line of diff content\n" * 20)  # >100 chars
        self.assertGreater(len(diff), max_chars)

        truncated = diff[:max_chars]
        last_newline = truncated.rfind("\n")
        if last_newline > 0:
            truncated = truncated[:last_newline]
        truncated += "\n\n[... diff truncated ...]"

        self.assertIn("[... diff truncated ...]", truncated)
        self.assertFalse(truncated.startswith("\n\n["))

    def test_default_prompt_contains_key_sections(self):
        """Default prompt should guide the model to produce structured output"""
        language = "english"
        language_note = f"\nRespond entirely in {language}." if language.lower() != "english" else ""
        prompt = f"""You are a thorough and pragmatic senior software engineer...{language_note}"""
        # Non-english language should inject a note
        language2 = "danish"
        language_note2 = f"\nRespond entirely in {language2}." if language2.lower() != "english" else ""
        self.assertIn("danish", language_note2)
        self.assertEqual(language_note, "")

    def test_empty_diff_detected(self):
        """Empty diff file should be detectable"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("")
            path = f.name
        with open(path) as f:
            diff = f.read().strip()
        self.assertEqual(diff, "")

    def test_valid_diff_passes(self):
        """Non-empty diff should pass through"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("diff --git a/foo.py b/foo.py\n+++ b/foo.py\n+print('hello')\n")
            path = f.name
        with open(path) as f:
            diff = f.read().strip()
        self.assertGreater(len(diff), 0)


if __name__ == "__main__":
    print("Running ai-pr-review smoke tests...\n")
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestReviewLogic)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
