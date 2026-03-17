"""tests/test_import_checker.py — Tests for cross-file import consistency checker."""
from __future__ import annotations

import pytest
from pathlib import Path


@pytest.fixture
def project(tmp_path):
    """Create a minimal project structure for import testing."""
    src = tmp_path / "src"
    src.mkdir()
    staging = tmp_path / "staging"
    staging.mkdir()
    return tmp_path, src, staging


class TestPythonImports:
    def test_valid_import_passes(self, project):
        from adelie.utils.import_checker import check_imports
        root, src, staging = project

        # Create two Python files that import each other
        (staging / "utils.py").write_text("def helper(): pass\n")
        (staging / "main.py").write_text("import utils\nutils.helper()\n")

        issues = check_imports(
            [{"filepath": "main.py"}, {"filepath": "utils.py"}],
            staging_root=staging,
            project_root=root,
        )
        assert len(issues) == 0

    def test_missing_import_detected(self, project):
        from adelie.utils.import_checker import check_imports
        root, src, staging = project

        (staging / "main.py").write_text("import nonexistent_module\n")

        issues = check_imports(
            [{"filepath": "main.py"}],
            staging_root=staging,
            project_root=root,
        )
        assert len(issues) == 1
        assert "nonexistent_module" in issues[0].imported

    def test_stdlib_imports_ignored(self, project):
        from adelie.utils.import_checker import check_imports
        root, src, staging = project

        (staging / "main.py").write_text(
            "import os\nimport json\nfrom pathlib import Path\nfrom datetime import datetime\n"
        )

        issues = check_imports(
            [{"filepath": "main.py"}],
            staging_root=staging,
            project_root=root,
        )
        assert len(issues) == 0

    def test_third_party_imports_ignored(self, project):
        from adelie.utils.import_checker import check_imports
        root, src, staging = project

        (staging / "main.py").write_text("import flask\nimport requests\n")

        issues = check_imports(
            [{"filepath": "main.py"}],
            staging_root=staging,
            project_root=root,
        )
        assert len(issues) == 0


class TestJSImports:
    def test_valid_relative_import_passes(self, project):
        from adelie.utils.import_checker import check_imports
        root, src, staging = project

        (staging / "src").mkdir(exist_ok=True)
        (staging / "src" / "utils.ts").write_text("export const x = 1;\n")
        (staging / "src" / "main.ts").write_text("import { x } from './utils';\n")

        issues = check_imports(
            [{"filepath": "src/main.ts"}, {"filepath": "src/utils.ts"}],
            staging_root=staging,
            project_root=root,
        )
        assert len(issues) == 0

    def test_missing_relative_import_detected(self, project):
        from adelie.utils.import_checker import check_imports
        root, src, staging = project

        (staging / "src").mkdir(exist_ok=True)
        (staging / "src" / "main.ts").write_text("import { x } from './nonexistent';\n")

        issues = check_imports(
            [{"filepath": "src/main.ts"}],
            staging_root=staging,
            project_root=root,
        )
        assert len(issues) == 1
        assert "./nonexistent" in issues[0].imported

    def test_npm_packages_ignored(self, project):
        from adelie.utils.import_checker import check_imports
        root, src, staging = project

        (staging / "src").mkdir(exist_ok=True)
        (staging / "src" / "main.ts").write_text("import React from 'react';\nimport express from 'express';\n")

        issues = check_imports(
            [{"filepath": "src/main.ts"}],
            staging_root=staging,
            project_root=root,
        )
        assert len(issues) == 0


class TestFormatIssues:
    def test_format_empty(self):
        from adelie.utils.import_checker import format_import_issues
        assert format_import_issues([]) == ""

    def test_format_with_issues(self):
        from adelie.utils.import_checker import format_import_issues, ImportIssue
        issues = [
            ImportIssue(file="main.py", line=3, imported="foo", reason="Module 'foo' not found"),
        ]
        result = format_import_issues(issues)
        assert "IMPORT CONSISTENCY ERRORS" in result
        assert "main.py" in result
        assert "foo" in result


class TestDiagnoseBuildError:
    def test_typescript_error_parsing(self):
        from adelie.agents.runner_ai import _diagnose_build_error
        stderr = "src/App.tsx:12:5 - error TS2304: Cannot find name 'foo'.\n"
        result = _diagnose_build_error(stderr)
        assert len(result) >= 1
        assert result[0]["file"] == "src/App.tsx"
        assert result[0]["line"] == 12
        assert result[0]["error_type"] == "TS2304"

    def test_python_error_parsing(self):
        from adelie.agents.runner_ai import _diagnose_build_error
        stderr = '  File "main.py", line 5\n    print(x\n         ^\nSyntaxError: unexpected EOF while parsing\n'
        result = _diagnose_build_error(stderr)
        assert len(result) >= 1
        assert "main.py" in result[0]["file"]
        assert result[0]["error_type"] == "PythonError"

    def test_general_error_fallback(self):
        from adelie.agents.runner_ai import _diagnose_build_error
        stderr = "npm ERR! Cannot find module 'express'\nnpm ERR! Failed at the build script.\n"
        result = _diagnose_build_error(stderr)
        assert len(result) >= 1
        assert result[0]["error_type"] == "BuildError"

    def test_empty_input(self):
        from adelie.agents.runner_ai import _diagnose_build_error
        result = _diagnose_build_error("", "")
        assert result == []
