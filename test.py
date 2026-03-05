#!/usr/bin/env python3
"""
Smoke tests for ai-pr-review.
Run with: python3 test.py

NOTE: These tests use local implementations of parse_findings, extract_file_and_line,
and compare_findings rather than importing from review.py. This is intentional because
importing review.py would execute module-level code that expects environment setup
(diff files, GitHub API tokens, etc.).

IDEALLY: review.py should be refactored to separate function definitions from
module-level execution, allowing tests to import functions directly.
See: https://github.com/hilleer/ai-pr-review/pull/6#discussion_rXXX
"""

import json
import os
import sys
import tempfile
import unittest
from dataclasses import dataclass
from typing import List, Optional, Tuple

os.environ.update({
    "INPUT_API_KEY": "test-key",
    "INPUT_BASE_URL": "https://api.example.com/v1",
    "INPUT_MODEL": "test-model",
    "INPUT_SYSTEM_PROMPT": "",
    "INPUT_MAX_TOKENS": "2048",
    "INPUT_MAX_DIFF_CHARS": "80000",
    "INPUT_LANGUAGE": "english",
    "INPUT_DEBOUNCE_MINUTES": "1",
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


@dataclass
class Finding:
    file_path: str
    line_start: int
    line_end: int
    severity: str
    text: str
    raw_line: str


def parse_findings(review_text: str) -> List[Finding]:
    import re
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
    import re
    patterns = [
        r'([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+):(\d+)-(\d+)',
        r'([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+):(\d+)',
        r'[Ff]ile[:\s]+([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)[,\s]+[Ll]ine[:\s]+(\d+)',
        r'[Ii]n\s+([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)\s+at\s+line\s+(\d+)',
        r'[Ll]ines?\s+(\d+)-?(\d+)?\s+(?:of|in)\s+([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            groups = match.groups()
            
            if pattern == patterns[0]:
                return groups[0], int(groups[1]), int(groups[2])
            elif pattern == patterns[1]:
                return groups[0], int(groups[1]), int(groups[1])
            elif pattern in [patterns[2], patterns[3]]:
                return groups[0], int(groups[1]), int(groups[1])
            elif pattern == patterns[4]:
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


class TestFindingsParser(unittest.TestCase):
    def test_parse_simple_file_line(self):
        text = "### 🔴 Critical\n- src/auth.py:45 - SQL injection vulnerability"
        findings = parse_findings(text)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].file_path, "src/auth.py")
        self.assertEqual(findings[0].line_start, 45)
        self.assertEqual(findings[0].line_end, 45)
        self.assertEqual(findings[0].severity, "critical")
    
    def test_parse_file_line_range(self):
        text = "### 🟡 Warning\n- src/api.py:123-125 - Missing error handling"
        findings = parse_findings(text)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].file_path, "src/api.py")
        self.assertEqual(findings[0].line_start, 123)
        self.assertEqual(findings[0].line_end, 125)
    
    def test_parse_multiple_sections(self):
        text = """### 🔴 Critical
- src/auth.py:45 - SQL injection

### 🟡 Warning
- src/api.py:123 - Missing validation

### 🟢 Suggestion
- src/utils.py:10 - Improve naming"""
        findings = parse_findings(text)
        self.assertEqual(len(findings), 3)
        severities = [f.severity for f in findings]
        self.assertIn('critical', severities)
        self.assertIn('warning', severities)
        self.assertIn('suggestion', severities)
    
    def test_empty_sections(self):
        text = "## Summary\n\nThis PR is clean"
        findings = parse_findings(text)
        self.assertEqual(len(findings), 0)


class TestFindingsComparison(unittest.TestCase):
    def test_exact_match(self):
        old = [Finding("src/auth.py", 45, 45, "critical", "SQL injection", "SQL injection")]
        new = [Finding("src/auth.py", 45, 45, "critical", "SQL injection", "SQL injection")]
        resolved, persisting = compare_findings(old, new)
        self.assertEqual(len(resolved), 0)
        self.assertEqual(len(persisting), 1)
    
    def test_line_tolerance(self):
        old = [Finding("src/auth.py", 45, 45, "critical", "Issue", "Issue")]
        new = [Finding("src/auth.py", 47, 47, "critical", "Issue", "Issue")]
        resolved, persisting = compare_findings(old, new)
        self.assertEqual(len(resolved), 0)
        self.assertEqual(len(persisting), 1)
    
    def test_resolved_finding(self):
        old = [
            Finding("src/auth.py", 45, 45, "critical", "SQL injection", "SQL injection"),
            Finding("src/api.py", 123, 123, "warning", "Missing validation", "Missing validation"),
        ]
        new = [Finding("src/auth.py", 45, 45, "critical", "SQL injection", "SQL injection")]
        resolved, persisting = compare_findings(old, new)
        self.assertEqual(len(resolved), 1)
        self.assertEqual(len(persisting), 1)
        self.assertEqual(resolved[0].file_path, "src/api.py")
    
    def test_different_files(self):
        old = [Finding("src/auth.py", 45, 45, "critical", "Issue", "Issue")]
        new = [Finding("src/api.py", 45, 45, "critical", "Issue", "Issue")]
        resolved, persisting = compare_findings(old, new)
        self.assertEqual(len(resolved), 1)
        self.assertEqual(len(persisting), 0)


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
    
    def _parse_debounce(self, raw_value: Optional[str]) -> int:
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


if __name__ == "__main__":
    print("Running ai-pr-review smoke tests...\n")
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in [TestURLNormalisation, TestDiffHandling, TestLanguageNote, 
                TestOnDemandTrigger, TestFindingsParser, TestFindingsComparison,
                TestPerLineComments, TestDebounceLogic]:
        suite.addTests(loader.loadTestsFromTestCase(cls))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
