"""
adelie/policy_engine.py

Declarative Policy Engine — enforces project constraints from constraints.yaml.

Sits between Reviewer AI and staging promotion in the pipeline:
  Coder → staging → verify → Reviewer → ⛔ PolicyGate → promote

Unlike Reviewer AI (LLM-based, probabilistic), the PolicyEngine is
deterministic: rules are checked via regex pattern matching, Python AST
analysis, and file-level metrics. Violations with severity "block" prevent
code from being promoted to the project root.

Users define policies in `.adelie/constraints.yaml`.
If no constraints file exists, the engine is a no-op.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from rich.console import Console

console = Console()


# ── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class PolicyViolation:
    """A single policy violation found in a file."""
    rule_id: str           # "no-raw-sql"
    rule_name: str         # "ORM 강제 — raw SQL 금지"
    file: str              # "src/db.py"
    line: int              # 42 (1-indexed, 0 if unknown)
    severity: str          # "block" | "warn" | "info"
    message: str           # User-facing message
    matched_text: str      # The offending code snippet
    autofix_hint: str      # Suggestion for fixing


@dataclass
class PolicyReport:
    """Aggregated result of policy checks across all files."""
    violations: list[PolicyViolation] = field(default_factory=list)

    @property
    def has_blockers(self) -> bool:
        """True if any violation has severity 'block'."""
        return any(v.severity == "block" for v in self.violations)

    @property
    def blocker_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "block")

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "warn")

    @property
    def info_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "info")

    def format_feedback(self) -> str:
        """Format violations as feedback for Coder AI retry."""
        if not self.violations:
            return ""

        lines = [
            f"## ⛔ POLICY VIOLATIONS ({len(self.violations)} issue(s))",
            "The following policy constraints were violated. Fix ALL blocking issues:",
            "",
        ]
        for v in self.violations:
            icon = "⛔" if v.severity == "block" else "⚠️" if v.severity == "warn" else "ℹ️"
            line_info = f" (line {v.line})" if v.line else ""
            lines.append(f"- {icon} **[{v.rule_id}]** `{v.file}`{line_info}: {v.message}")
            if v.matched_text:
                snippet = v.matched_text[:80].replace("\n", " ")
                lines.append(f"  Matched: `{snippet}`")
            if v.autofix_hint:
                lines.append(f"  Fix: {v.autofix_hint}")
            lines.append("")

        return "\n".join(lines)

    def format_log(self) -> str:
        """Format violations as a log entry."""
        if not self.violations:
            return "PolicyGate: all checks passed ✅"

        parts = [f"PolicyGate: {len(self.violations)} violation(s) found"]
        parts.append(f"  ⛔ {self.blocker_count} blocking | ⚠️ {self.warning_count} warnings | ℹ️ {self.info_count} info")
        for v in self.violations:
            parts.append(f"  [{v.severity.upper()}] {v.rule_id}: {v.file}:{v.line} — {v.message}")
        return "\n".join(parts)


# ── Language Mapping ─────────────────────────────────────────────────────────

_LANG_BY_EXT: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".sql": "sql",
}


def _detect_language(filepath: str) -> str:
    """Detect language from file extension."""
    ext = Path(filepath).suffix.lower()
    return _LANG_BY_EXT.get(ext, "")


# ── Policy Rule ──────────────────────────────────────────────────────────────


@dataclass
class PolicyRule:
    """A single policy rule parsed from constraints.yaml."""
    id: str
    name: str
    rule_type: str          # "pattern" | "ast" | "file"
    languages: list[str]    # ["python", "javascript"] — empty = all
    severity: str           # "block" | "warn" | "info"
    message: str
    autofix_hint: str

    # Pattern-specific
    pattern: str = ""
    negative_pattern: str = ""   # If present AND matches, rule passes

    # AST-specific
    ast_check: str = ""          # "disallow_calls", "disallow_import_star", "require_docstrings"
    target_calls: list[str] = field(default_factory=list)
    scope: str = ""              # "public_functions" | "all_functions" | "classes"

    # File-specific
    max_lines: int = 0

    def applies_to(self, language: str) -> bool:
        """Check if this rule applies to the given language."""
        if not self.languages:
            return True
        return language in self.languages

    def check_pattern(self, content: str, filepath: str) -> list[PolicyViolation]:
        """Run regex pattern check against file content."""
        if self.rule_type != "pattern" or not self.pattern:
            return []

        violations: list[PolicyViolation] = []
        try:
            compiled = re.compile(self.pattern, re.IGNORECASE | re.MULTILINE)
        except re.error:
            return []

        # If negative_pattern exists, check if the file passes
        neg_compiled = None
        if self.negative_pattern:
            try:
                neg_compiled = re.compile(self.negative_pattern, re.IGNORECASE)
            except re.error:
                pass

        for line_num, line in enumerate(content.splitlines(), 1):
            match = compiled.search(line)
            if match:
                # Check negative pattern — if it matches this line, skip
                if neg_compiled and neg_compiled.search(line):
                    continue

                violations.append(PolicyViolation(
                    rule_id=self.id,
                    rule_name=self.name,
                    file=filepath,
                    line=line_num,
                    severity=self.severity,
                    message=self.message,
                    matched_text=match.group(0),
                    autofix_hint=self.autofix_hint,
                ))

        return violations

    def check_file_rules(self, content: str, filepath: str) -> list[PolicyViolation]:
        """Run file-level checks (line count, etc.)."""
        if self.rule_type != "file":
            return []

        violations: list[PolicyViolation] = []

        if self.max_lines > 0:
            line_count = content.count("\n") + 1
            if line_count > self.max_lines:
                violations.append(PolicyViolation(
                    rule_id=self.id,
                    rule_name=self.name,
                    file=filepath,
                    line=0,
                    severity=self.severity,
                    message=f"{self.message} ({line_count} lines, max {self.max_lines})",
                    matched_text="",
                    autofix_hint=self.autofix_hint,
                ))

        return violations

    def check_ast(self, content: str, filepath: str) -> list[PolicyViolation]:
        """Run AST-based checks (Python only)."""
        if self.rule_type != "ast":
            return []

        try:
            from adelie.utils.ast_checker import run_ast_check
            return run_ast_check(
                content=content,
                filepath=filepath,
                check_type=self.ast_check,
                rule_id=self.id,
                rule_name=self.name,
                severity=self.severity,
                message=self.message,
                autofix_hint=self.autofix_hint,
                target_calls=self.target_calls,
                scope=self.scope,
            )
        except ImportError:
            return []
        except Exception:
            return []


# ── PolicyEngine ─────────────────────────────────────────────────────────────


class PolicyEngine:
    """
    Loads and enforces project-specific constraints from constraints.yaml.

    Usage:
        engine = PolicyEngine()
        report = engine.check_all(written_files, staging_root)
        if report.has_blockers:
            # Block promotion
    """

    def __init__(self, constraints_path: Path | None = None):
        if constraints_path is None:
            try:
                from adelie.config import PROJECT_ROOT
                constraints_path = PROJECT_ROOT / ".adelie" / "constraints.yaml"
            except Exception:
                constraints_path = Path.cwd() / ".adelie" / "constraints.yaml"

        self._path = constraints_path
        self._rules: list[PolicyRule] = []
        self._loaded = False
        self._load()

    def _load(self) -> None:
        """Load and parse constraints.yaml."""
        if not self._path.exists():
            self._loaded = True
            return

        try:
            # Use built-in yaml-like parsing to avoid adding pyyaml dependency
            content = self._path.read_text(encoding="utf-8")
            data = self._parse_yaml(content)
            if not isinstance(data, dict):
                self._loaded = True
                return

            version = data.get("version", 1)
            default_severity = data.get("severity", "block")
            raw_rules = data.get("rules", [])

            for rule_data in raw_rules:
                if not isinstance(rule_data, dict):
                    continue
                rule = self._parse_rule(rule_data, default_severity)
                if rule:
                    self._rules.append(rule)

            self._loaded = True
        except Exception as e:
            console.print(f"[yellow]⚠️ constraints.yaml parse error: {e}[/yellow]")
            self._loaded = True

    def _parse_yaml(self, content: str) -> dict | list | None:
        """
        Parse YAML content. Try PyYAML first, fall back to json if installed,
        then to a minimal built-in parser.
        """
        # Try PyYAML
        try:
            import yaml
            return yaml.safe_load(content)
        except ImportError:
            pass

        # Minimal YAML-subset parser for constraints.yaml
        return self._minimal_yaml_parse(content)

    def _minimal_yaml_parse(self, content: str) -> dict:
        """
        Minimal YAML parser that handles the constraints.yaml schema.
        Supports: scalars, lists (inline [...] and dash-prefixed), nested dicts.
        Does NOT support: multi-line strings, anchors, complex YAML features.
        """
        import json as _json

        result: dict = {}
        current_list: list | None = None
        current_list_key: str = ""
        current_item: dict | None = None
        indent_stack: list[tuple[int, dict | list]] = [(0, result)]

        for raw_line in content.splitlines():
            stripped = raw_line.strip()

            # Skip empty lines and comments
            if not stripped or stripped.startswith("#"):
                continue

            indent = len(raw_line) - len(raw_line.lstrip())

            # List item (- key: value or just - value)
            if stripped.startswith("- "):
                item_content = stripped[2:].strip()

                if current_list is not None:
                    if ":" in item_content:
                        # Start of a new dict item in the list
                        current_item = {}
                        current_list.append(current_item)
                        key, val = item_content.split(":", 1)
                        key = key.strip()
                        val = val.strip()
                        current_item[key] = self._parse_scalar(val)
                    else:
                        # Simple list item
                        current_list.append(self._parse_scalar(item_content))
                continue

            # Key: value pair
            if ":" in stripped:
                key, val = stripped.split(":", 1)
                key = key.strip()
                val = val.strip()

                if not val:
                    # Start of a nested structure — next lines will tell us what
                    current_list = None
                    current_list_key = key
                    current_item = None
                    continue

                if val.startswith("[") and val.endswith("]"):
                    # Inline list
                    items = [self._parse_scalar(i.strip()) for i in val[1:-1].split(",") if i.strip()]
                    result[key] = items
                    continue

                # Regular key: value in current context
                if current_item is not None:
                    current_item[key] = self._parse_scalar(val)
                else:
                    result[key] = self._parse_scalar(val)
                continue

            # If we get here after a key with no value, it's a list start
            if current_list_key and current_list is None:
                current_list = []
                result[current_list_key] = current_list

        # Handle the case where rules list wasn't populated
        if current_list_key and current_list_key not in result:
            result[current_list_key] = []

        return result

    def _parse_scalar(self, val: str) -> Any:
        """Parse a YAML scalar value."""
        if not val or val == "~" or val == "null":
            return None
        if val.lower() == "true":
            return True
        if val.lower() == "false":
            return False
        # Try integer
        try:
            return int(val)
        except ValueError:
            pass
        # Try float
        try:
            return float(val)
        except ValueError:
            pass
        # String — strip quotes
        if (val.startswith("'") and val.endswith("'")) or \
           (val.startswith('"') and val.endswith('"')):
            return val[1:-1]
        return val

    def _parse_rule(self, data: dict, default_severity: str) -> PolicyRule | None:
        """Parse a single rule dict into a PolicyRule."""
        rule_id = data.get("id")
        if not rule_id:
            return None

        languages = data.get("languages", [])
        if isinstance(languages, str):
            languages = [languages]

        target_calls = data.get("target_calls", [])
        if isinstance(target_calls, str):
            target_calls = [target_calls]

        return PolicyRule(
            id=rule_id,
            name=data.get("name", rule_id),
            rule_type=data.get("type", "pattern"),
            languages=languages,
            severity=data.get("severity", default_severity),
            message=data.get("message", ""),
            autofix_hint=data.get("autofix_hint", ""),
            pattern=data.get("pattern", ""),
            negative_pattern=data.get("negative_pattern", ""),
            ast_check=data.get("ast_check", ""),
            target_calls=target_calls,
            scope=data.get("scope", ""),
            max_lines=data.get("max_lines", 0),
        )

    # ── Public API ───────────────────────────────────────────────────────

    @property
    def rules(self) -> list[PolicyRule]:
        """Return loaded rules."""
        return list(self._rules)

    @property
    def has_rules(self) -> bool:
        """True if any rules are loaded."""
        return len(self._rules) > 0

    def check_file(
        self,
        filepath: str,
        content: str,
        language: str = "",
    ) -> list[PolicyViolation]:
        """
        Check a single file against all applicable rules.

        Args:
            filepath: Relative file path
            content: File content
            language: Language (auto-detected from extension if empty)

        Returns:
            List of violations found.
        """
        if not self._rules:
            return []

        if not language:
            language = _detect_language(filepath)

        violations: list[PolicyViolation] = []

        for rule in self._rules:
            if not rule.applies_to(language):
                continue

            if rule.rule_type == "pattern":
                violations.extend(rule.check_pattern(content, filepath))
            elif rule.rule_type == "ast" and language == "python":
                violations.extend(rule.check_ast(content, filepath))
            elif rule.rule_type == "file":
                violations.extend(rule.check_file_rules(content, filepath))

        return violations

    def check_all(
        self,
        files: list[dict],
        staging_root: Path,
    ) -> PolicyReport:
        """
        Check all staged files against policy rules.

        Args:
            files: list of {"filepath": ...} dicts
            staging_root: Root directory of staged files

        Returns:
            PolicyReport with all violations.
        """
        report = PolicyReport()

        if not self._rules:
            return report

        for finfo in files:
            filepath = finfo.get("filepath", "")
            if not filepath:
                continue

            full_path = staging_root / filepath
            if not full_path.exists():
                continue

            try:
                content = full_path.read_text(encoding="utf-8")
            except Exception:
                continue

            violations = self.check_file(filepath, content)
            report.violations.extend(violations)

        return report

    def get_prompt_summary(self) -> str:
        """
        Get a summary of active policies for injection into agent prompts.
        Returns empty string if no rules exist.
        """
        if not self._rules:
            return ""

        lines = [
            "\n## ⛔ Active Policy Constraints (from .adelie/constraints.yaml)",
            "The following constraints are ENFORCED. Violating 'block' rules will prevent your code from being promoted.",
            "",
        ]

        for rule in self._rules:
            icon = "⛔" if rule.severity == "block" else "⚠️" if rule.severity == "warn" else "ℹ️"
            lang_str = f" [{', '.join(rule.languages)}]" if rule.languages else ""
            lines.append(f"- {icon} **{rule.id}**: {rule.message}{lang_str}")
            if rule.autofix_hint:
                lines.append(f"  → {rule.autofix_hint}")

        lines.append("")
        return "\n".join(lines)
