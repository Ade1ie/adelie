"""
tests/test_policy_engine.py

Tests for the PolicyEngine — declarative constraint enforcement.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest


# ── PolicyReport Tests ───────────────────────────────────────────────────────


class TestPolicyViolation:
    def test_basic_creation(self):
        from adelie.policy_engine import PolicyViolation
        v = PolicyViolation(
            rule_id="no-eval",
            rule_name="eval 금지",
            file="src/app.py",
            line=10,
            severity="block",
            message="eval() 사용 금지",
            matched_text="eval(user_input)",
            autofix_hint="ast.literal_eval()을 사용하세요.",
        )
        assert v.rule_id == "no-eval"
        assert v.severity == "block"
        assert v.line == 10


class TestPolicyReport:
    def test_empty_report(self):
        from adelie.policy_engine import PolicyReport
        report = PolicyReport()
        assert not report.has_blockers
        assert report.blocker_count == 0
        assert report.warning_count == 0
        assert report.format_feedback() == ""
        assert "passed" in report.format_log()

    def test_report_with_blockers(self):
        from adelie.policy_engine import PolicyReport, PolicyViolation
        report = PolicyReport(violations=[
            PolicyViolation("r1", "Rule 1", "a.py", 1, "block", "msg1", "", ""),
            PolicyViolation("r2", "Rule 2", "b.py", 2, "warn", "msg2", "", ""),
            PolicyViolation("r3", "Rule 3", "c.py", 3, "info", "msg3", "", ""),
        ])
        assert report.has_blockers
        assert report.blocker_count == 1
        assert report.warning_count == 1
        assert report.info_count == 1

    def test_report_without_blockers(self):
        from adelie.policy_engine import PolicyReport, PolicyViolation
        report = PolicyReport(violations=[
            PolicyViolation("r1", "Rule 1", "a.py", 1, "warn", "msg1", "", ""),
            PolicyViolation("r2", "Rule 2", "b.py", 2, "info", "msg2", "", ""),
        ])
        assert not report.has_blockers

    def test_format_feedback(self):
        from adelie.policy_engine import PolicyReport, PolicyViolation
        report = PolicyReport(violations=[
            PolicyViolation("no-eval", "eval 금지", "app.py", 10, "block",
                            "eval() 금지", "eval(x)", "ast.literal_eval 사용"),
        ])
        fb = report.format_feedback()
        assert "⛔ POLICY VIOLATIONS" in fb
        assert "no-eval" in fb
        assert "app.py" in fb
        assert "eval(x)" in fb
        assert "ast.literal_eval" in fb


# ── Language Detection ───────────────────────────────────────────────────────


class TestLanguageDetection:
    def test_python(self):
        from adelie.policy_engine import _detect_language
        assert _detect_language("src/app.py") == "python"

    def test_javascript(self):
        from adelie.policy_engine import _detect_language
        assert _detect_language("src/index.js") == "javascript"

    def test_typescript(self):
        from adelie.policy_engine import _detect_language
        assert _detect_language("src/app.tsx") == "typescript"

    def test_unknown(self):
        from adelie.policy_engine import _detect_language
        assert _detect_language("README.md") == ""


# ── PolicyRule Pattern Checks ────────────────────────────────────────────────


class TestPolicyRulePattern:
    def _make_rule(self, **kwargs):
        from adelie.policy_engine import PolicyRule
        defaults = dict(
            id="test-rule",
            name="Test Rule",
            rule_type="pattern",
            languages=["python"],
            severity="block",
            message="violation",
            autofix_hint="fix it",
            pattern="",
            negative_pattern="",
            ast_check="",
            target_calls=[],
            scope="",
            max_lines=0,
        )
        defaults.update(kwargs)
        return PolicyRule(**defaults)

    def test_simple_pattern_match(self):
        rule = self._make_rule(pattern=r"eval\(")
        code = "result = eval(user_input)"
        violations = rule.check_pattern(code, "app.py")
        assert len(violations) == 1
        assert violations[0].line == 1
        assert "eval(" in violations[0].matched_text

    def test_pattern_no_match(self):
        rule = self._make_rule(pattern=r"eval\(")
        code = "result = safe_function(user_input)"
        violations = rule.check_pattern(code, "app.py")
        assert len(violations) == 0

    def test_multiline_pattern(self):
        rule = self._make_rule(pattern=r"cursor\.execute")
        code = textwrap.dedent("""\
            import db
            cursor.execute("SELECT * FROM users")
            print("done")
            cursor.execute("DELETE FROM logs")
        """)
        violations = rule.check_pattern(code, "db.py")
        assert len(violations) == 2
        assert violations[0].line == 2
        assert violations[1].line == 4

    def test_negative_pattern(self):
        """If negative pattern matches, the violation is suppressed."""
        rule = self._make_rule(
            pattern=r"requests\.(get|post)",
            negative_pattern=r"timeout\s*=",
        )
        code_bad = 'requests.get("https://api.example.com")'
        code_good = 'requests.get("https://api.example.com", timeout=3)'

        assert len(rule.check_pattern(code_bad, "api.py")) == 1
        assert len(rule.check_pattern(code_good, "api.py")) == 0

    def test_invalid_pattern(self):
        rule = self._make_rule(pattern=r"[invalid")
        violations = rule.check_pattern("anything", "file.py")
        assert len(violations) == 0

    def test_language_filter(self):
        rule = self._make_rule(languages=["javascript"])
        assert not rule.applies_to("python")
        assert rule.applies_to("javascript")

    def test_empty_language_matches_all(self):
        rule = self._make_rule(languages=[])
        assert rule.applies_to("python")
        assert rule.applies_to("javascript")

    def test_wrong_rule_type(self):
        rule = self._make_rule(rule_type="ast", pattern=r"eval\(")
        violations = rule.check_pattern("eval(x)", "app.py")
        assert len(violations) == 0


# ── PolicyRule File Checks ───────────────────────────────────────────────────


class TestPolicyRuleFile:
    def _make_rule(self, **kwargs):
        from adelie.policy_engine import PolicyRule
        defaults = dict(
            id="max-lines",
            name="Max Lines",
            rule_type="file",
            languages=[],
            severity="warn",
            message="File too long",
            autofix_hint="Split it",
            pattern="",
            negative_pattern="",
            ast_check="",
            target_calls=[],
            scope="",
            max_lines=10,
        )
        defaults.update(kwargs)
        return PolicyRule(**defaults)

    def test_file_under_limit(self):
        rule = self._make_rule(max_lines=10)
        code = "\n".join(f"line_{i}" for i in range(5))
        assert len(rule.check_file_rules(code, "small.py")) == 0

    def test_file_over_limit(self):
        rule = self._make_rule(max_lines=10)
        code = "\n".join(f"line_{i}" for i in range(20))
        violations = rule.check_file_rules(code, "big.py")
        assert len(violations) == 1
        assert "20 lines" in violations[0].message


# ── PolicyEngine Integration ─────────────────────────────────────────────────


class TestPolicyEngine:
    def test_no_constraints_file(self, tmp_path):
        """Engine is a no-op when constraints.yaml doesn't exist."""
        from adelie.policy_engine import PolicyEngine
        engine = PolicyEngine(constraints_path=tmp_path / "nonexistent.yaml")
        assert not engine.has_rules
        report = engine.check_all([], tmp_path)
        assert not report.has_blockers
        assert engine.get_prompt_summary() == ""

    def test_empty_constraints(self, tmp_path):
        """Engine handles empty constraints file."""
        from adelie.policy_engine import PolicyEngine
        (tmp_path / "constraints.yaml").write_text("", encoding="utf-8")
        engine = PolicyEngine(constraints_path=tmp_path / "constraints.yaml")
        assert not engine.has_rules

    def test_check_file_with_pattern_rule(self, tmp_path):
        """Check a single Python file with a pattern rule."""
        from adelie.policy_engine import PolicyEngine

        # Write YAML-like constraints using PyYAML if available, else basic format
        yaml_content = textwrap.dedent("""\
            version: 1
            severity: block
        """)
        (tmp_path / "constraints.yaml").write_text(yaml_content, encoding="utf-8")

        engine = PolicyEngine(constraints_path=tmp_path / "constraints.yaml")
        # Manually add a rule (since YAML parsing of rules list is complex without PyYAML)
        from adelie.policy_engine import PolicyRule
        engine._rules.append(PolicyRule(
            id="no-eval",
            name="No eval",
            rule_type="pattern",
            languages=["python"],
            severity="block",
            message="eval is forbidden",
            autofix_hint="use ast.literal_eval",
            pattern=r"eval\(",
        ))

        violations = engine.check_file("app.py", 'x = eval(input())', "python")
        assert len(violations) == 1
        assert violations[0].rule_id == "no-eval"

    def test_check_all_with_staging(self, tmp_path):
        """Integration test: check staged files."""
        from adelie.policy_engine import PolicyEngine, PolicyRule

        engine = PolicyEngine(constraints_path=tmp_path / "none.yaml")
        engine._rules.append(PolicyRule(
            id="no-exec",
            name="No exec",
            rule_type="pattern",
            languages=["python"],
            severity="block",
            message="exec is forbidden",
            autofix_hint="",
            pattern=r"\bexec\(",
        ))

        # Create staged files
        staging = tmp_path / "staging"
        staging.mkdir()
        (staging / "good.py").write_text("print('hello')\n", encoding="utf-8")
        (staging / "bad.py").write_text("exec(user_code)\n", encoding="utf-8")

        files = [{"filepath": "good.py"}, {"filepath": "bad.py"}]
        report = engine.check_all(files, staging)

        assert report.has_blockers
        assert report.blocker_count == 1
        assert report.violations[0].file == "bad.py"

    def test_prompt_summary(self, tmp_path):
        from adelie.policy_engine import PolicyEngine, PolicyRule
        engine = PolicyEngine(constraints_path=tmp_path / "none.yaml")
        engine._rules.append(PolicyRule(
            id="no-secrets",
            name="No Secrets",
            rule_type="pattern",
            languages=[],
            severity="block",
            message="Do not hardcode secrets",
            autofix_hint="Use env vars",
            pattern=r"api_key\s*=\s*['\"]",
        ))
        summary = engine.get_prompt_summary()
        assert "Active Policy Constraints" in summary
        assert "no-secrets" in summary
        assert "Do not hardcode secrets" in summary

    def test_mixed_severities(self, tmp_path):
        """Blockers block, warnings don't."""
        from adelie.policy_engine import PolicyEngine, PolicyRule

        engine = PolicyEngine(constraints_path=tmp_path / "none.yaml")
        engine._rules.append(PolicyRule(
            id="blocker",
            name="Blocker",
            rule_type="pattern",
            languages=["python"],
            severity="block",
            message="blocked",
            autofix_hint="",
            pattern=r"BANNED_FUNCTION",
        ))
        engine._rules.append(PolicyRule(
            id="warner",
            name="Warner",
            rule_type="pattern",
            languages=["python"],
            severity="warn",
            message="warned",
            autofix_hint="",
            pattern=r"TODO",
        ))

        staging = tmp_path / "staging"
        staging.mkdir()
        (staging / "code.py").write_text("x = 1  # TODO: refactor\n", encoding="utf-8")

        files = [{"filepath": "code.py"}]
        report = engine.check_all(files, staging)

        assert not report.has_blockers  # Only a warning
        assert report.warning_count == 1


# ── AST Checker Tests ────────────────────────────────────────────────────────


class TestASTChecker:
    def test_disallow_calls_eval(self):
        from adelie.utils.ast_checker import run_ast_check
        code = textwrap.dedent("""\
            x = 1
            result = eval("x + 1")
            print(result)
        """)
        violations = run_ast_check(
            content=code,
            filepath="test.py",
            check_type="disallow_calls",
            rule_id="no-eval",
            rule_name="No eval",
            severity="block",
            message="eval is forbidden",
            target_calls=["eval", "exec"],
        )
        assert len(violations) == 1
        assert violations[0].line == 2
        assert "eval" in violations[0].matched_text

    def test_disallow_calls_exec(self):
        from adelie.utils.ast_checker import run_ast_check
        code = 'exec("import os")'
        violations = run_ast_check(
            content=code,
            filepath="test.py",
            check_type="disallow_calls",
            rule_id="no-exec",
            rule_name="No exec",
            severity="block",
            message="exec is forbidden",
            target_calls=["exec"],
        )
        assert len(violations) == 1

    def test_disallow_calls_none_found(self):
        from adelie.utils.ast_checker import run_ast_check
        code = "x = int('42')"
        violations = run_ast_check(
            content=code,
            filepath="test.py",
            check_type="disallow_calls",
            rule_id="no-eval",
            rule_name="No eval",
            severity="block",
            message="eval is forbidden",
            target_calls=["eval"],
        )
        assert len(violations) == 0

    def test_disallow_import_star(self):
        from adelie.utils.ast_checker import run_ast_check
        code = textwrap.dedent("""\
            from os import path
            from sys import *
            import json
        """)
        violations = run_ast_check(
            content=code,
            filepath="test.py",
            check_type="disallow_import_star",
            rule_id="no-star",
            rule_name="No wildcard",
            severity="warn",
            message="Wildcard imports forbidden",
        )
        assert len(violations) == 1
        assert violations[0].line == 2
        assert "sys" in violations[0].matched_text

    def test_disallow_import_star_none_found(self):
        from adelie.utils.ast_checker import run_ast_check
        code = "from os import path\nimport json\n"
        violations = run_ast_check(
            content=code,
            filepath="test.py",
            check_type="disallow_import_star",
            rule_id="no-star",
            rule_name="No wildcard",
            severity="warn",
            message="Wildcard imports forbidden",
        )
        assert len(violations) == 0

    def test_require_docstrings_public(self):
        from adelie.utils.ast_checker import run_ast_check
        code = textwrap.dedent("""\
            def public_func():
                pass

            def _private_func():
                pass

            def documented_func():
                \"\"\"This has a docstring.\"\"\"
                pass
        """)
        violations = run_ast_check(
            content=code,
            filepath="test.py",
            check_type="require_docstrings",
            rule_id="docstrings",
            rule_name="Require docstrings",
            severity="warn",
            message="Missing docstring",
            scope="public_functions",
        )
        # Only public_func should be flagged (documented_func has docstring, _private is skipped)
        assert len(violations) == 1
        assert "public_func" in violations[0].matched_text

    def test_syntax_error_skips_ast(self):
        from adelie.utils.ast_checker import run_ast_check
        code = "def broken(:\n    pass"
        violations = run_ast_check(
            content=code,
            filepath="test.py",
            check_type="disallow_calls",
            rule_id="no-eval",
            rule_name="No eval",
            severity="block",
            message="eval",
            target_calls=["eval"],
        )
        assert len(violations) == 0  # Gracefully skip

    def test_multiple_forbidden_calls(self):
        from adelie.utils.ast_checker import run_ast_check
        code = textwrap.dedent("""\
            eval("1+1")
            exec("print('hi')")
            compile("x=1", "<str>", "exec")
        """)
        violations = run_ast_check(
            content=code,
            filepath="test.py",
            check_type="disallow_calls",
            rule_id="no-dangerous",
            rule_name="No dangerous calls",
            severity="block",
            message="Forbidden",
            target_calls=["eval", "exec", "compile"],
        )
        assert len(violations) == 3


# ── Minimal YAML Parser Tests ───────────────────────────────────────────────


class TestMinimalYamlParser:
    def test_simple_scalars(self):
        from adelie.policy_engine import PolicyEngine
        engine = PolicyEngine.__new__(PolicyEngine)
        result = engine._minimal_yaml_parse("version: 1\nseverity: block\n")
        assert result["version"] == 1
        assert result["severity"] == "block"

    def test_inline_list(self):
        from adelie.policy_engine import PolicyEngine
        engine = PolicyEngine.__new__(PolicyEngine)
        result = engine._minimal_yaml_parse("languages: [python, javascript]\n")
        assert result["languages"] == ["python", "javascript"]

    def test_boolean_values(self):
        from adelie.policy_engine import PolicyEngine
        engine = PolicyEngine.__new__(PolicyEngine)
        result = engine._minimal_yaml_parse("enabled: true\ndisabled: false\n")
        assert result["enabled"] is True
        assert result["disabled"] is False

    def test_null_values(self):
        from adelie.policy_engine import PolicyEngine
        engine = PolicyEngine.__new__(PolicyEngine)
        result = engine._minimal_yaml_parse("value: null\nalt: ~\n")
        assert result["value"] is None
        assert result["alt"] is None

    def test_quoted_strings(self):
        from adelie.policy_engine import PolicyEngine
        engine = PolicyEngine.__new__(PolicyEngine)
        result = engine._minimal_yaml_parse("message: 'hello world'\n")
        assert result["message"] == "hello world"

    def test_parse_scalar_types(self):
        from adelie.policy_engine import PolicyEngine
        engine = PolicyEngine.__new__(PolicyEngine)
        assert engine._parse_scalar("42") == 42
        assert engine._parse_scalar("3.14") == 3.14
        assert engine._parse_scalar("true") is True
        assert engine._parse_scalar("false") is False
        assert engine._parse_scalar("null") is None
        assert engine._parse_scalar("hello") == "hello"
        assert engine._parse_scalar("'quoted'") == "quoted"
