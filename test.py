#!/usr/bin/env python3
"""
Smoke tests for ai-pr-review.
Run with: python3 test.py
"""

import json
import os
import sys
import tempfile
import unittest

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


class TestURLNormalisation(unittest.TestCase):
    def _normalise(self, base):
        base = base.rstrip("/")
        return base if base.endswith("/chat/completions") else f"{base}/chat/completions"

    def test_plain_base_url(self):
        self.assertEqual(
            self._normalise("https://api.openai.com/v1"),
            "https://api.openai.com/v1/chat/completions",
        )

    def test_already_has_completions_path(self):
        url = "https://api.openai.com/v1/chat/completions"
        self.assertEqual(self._normalise(url), url)

    def test_trailing_slash_stripped(self):
        self.assertEqual(
            self._normalise("https://api.moonshot.cn/v1/"),
            "https://api.moonshot.cn/v1/chat/completions",
        )

    def test_zhipu_url(self):
        self.assertEqual(
            self._normalise("https://open.bigmodel.cn/api/paas/v4"),
            "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        )


class TestDiffHandling(unittest.TestCase):
    def test_truncation_at_newline(self):
        max_chars = 100
        diff = "line of diff content\n" * 20
        self.assertGreater(len(diff), max_chars)

        truncated = diff[:max_chars]
        last_newline = truncated.rfind("\n")
        if last_newline > 0:
            truncated = truncated[:last_newline]
        truncated += "\n\n[... diff truncated ...]"

        self.assertIn("[... diff truncated ...]", truncated)
        self.assertNotIn("\n\n[... diff truncated ...]", diff[:max_chars])

    def test_empty_diff_detected(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("")
            path = f.name
        with open(path) as f:
            diff = f.read().strip()
        self.assertEqual(diff, "")

    def test_valid_diff_passes(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("diff --git a/foo.py b/foo.py\n+++ b/foo.py\n+print('hello')\n")
            path = f.name
        with open(path) as f:
            diff = f.read().strip()
        self.assertGreater(len(diff), 0)


class TestLanguageNote(unittest.TestCase):
    def _note(self, language):
        return f"\nRespond entirely in {language}." if language.lower() != "english" else ""

    def test_english_no_note(self):
        self.assertEqual(self._note("english"), "")

    def test_danish_adds_note(self):
        self.assertIn("danish", self._note("danish"))

    def test_german_adds_note(self):
        self.assertIn("german", self._note("german"))


class TestOnDemandTrigger(unittest.TestCase):
    """
    Simulates the comment-matching logic used in the issue_comment workflow.
    The actual filtering happens in the workflow `if:` condition, but we can
    test the equivalent Python logic here.
    """

    def _should_trigger(self, comment_body: str, phrase: str) -> bool:
        return phrase.strip().lower() in comment_body.strip().lower()

    def test_exact_phrase_triggers(self):
        self.assertTrue(self._should_trigger("/ai-review", "/ai-review"))

    def test_phrase_in_longer_comment_triggers(self):
        self.assertTrue(self._should_trigger(
            "Looks good, but /ai-review please before we merge",
            "/ai-review",
        ))

    def test_wrong_phrase_does_not_trigger(self):
        self.assertFalse(self._should_trigger("LGTM!", "/ai-review"))

    def test_custom_phrase(self):
        self.assertTrue(self._should_trigger("@bot please review", "@bot please review"))

    def test_case_insensitive(self):
        self.assertTrue(self._should_trigger("/AI-REVIEW", "/ai-review"))


if __name__ == "__main__":
    print("Running ai-pr-review smoke tests...\n")
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in [TestURLNormalisation, TestDiffHandling, TestLanguageNote, TestOnDemandTrigger]:
        suite.addTests(loader.loadTestsFromTestCase(cls))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
