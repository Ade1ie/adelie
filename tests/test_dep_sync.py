"""tests/test_dep_sync.py — Tests for dependency synchronization."""
from __future__ import annotations

import json

import pytest


class TestExtractJsImports:
    def test_basic_import(self):
        from adelie.utils.dep_sync import _extract_js_imports
        result = _extract_js_imports("import React from 'react'")
        # react is in builtins, shouldn't be returned
        assert "react" not in result

    def test_third_party_import(self):
        from adelie.utils.dep_sync import _extract_js_imports
        result = _extract_js_imports("import { DndProvider } from 'react-dnd'")
        assert "react-dnd" in result

    def test_scoped_import(self):
        from adelie.utils.dep_sync import _extract_js_imports
        result = _extract_js_imports("import { render } from '@testing-library/react'")
        assert "@testing-library/react" in result

    def test_relative_import_ignored(self):
        from adelie.utils.dep_sync import _extract_js_imports
        result = _extract_js_imports("import App from './App'")
        assert len(result) == 0

    def test_require_syntax(self):
        from adelie.utils.dep_sync import _extract_js_imports
        result = _extract_js_imports("const chess = require('chess.js')")
        assert "chess.js" in result


class TestScanMissingDeps:
    def test_detects_missing_js_deps(self, tmp_path):
        from adelie.utils.dep_sync import scan_missing_deps

        staging = tmp_path / "staging"
        staging.mkdir()
        (staging / "app.tsx").write_text(
            "import { Chess } from 'chess.js'\nimport { DndProvider } from 'react-dnd'"
        )

        project = tmp_path / "project"
        project.mkdir()
        (project / "package.json").write_text(json.dumps({
            "dependencies": {"react-dnd": "^16.0.0"}
        }))

        result = scan_missing_deps(
            [{"filepath": "app.tsx"}],
            staging, project,
        )

        assert "chess.js" in result
        assert "react-dnd" not in result

    def test_no_missing_with_empty_files(self, tmp_path):
        from adelie.utils.dep_sync import scan_missing_deps

        result = scan_missing_deps([], tmp_path, tmp_path)
        assert result == []


class TestSyncPackageJson:
    def test_adds_missing_deps(self, tmp_path):
        from adelie.utils.dep_sync import sync_package_json

        pkg = {"dependencies": {"react": "^18.0.0"}}
        pkg_path = tmp_path / "package.json"
        pkg_path.write_text(json.dumps(pkg))

        added = sync_package_json(["chess.js", "axios"], tmp_path)
        assert added == 2

        updated = json.loads(pkg_path.read_text())
        assert "chess.js" in updated["dependencies"]
        assert "axios" in updated["dependencies"]

    def test_no_duplicates(self, tmp_path):
        from adelie.utils.dep_sync import sync_package_json

        pkg = {"dependencies": {"chess.js": "^1.0.0"}}
        pkg_path = tmp_path / "package.json"
        pkg_path.write_text(json.dumps(pkg))

        added = sync_package_json(["chess.js"], tmp_path)
        assert added == 0

    def test_dev_deps_heuristic(self, tmp_path):
        from adelie.utils.dep_sync import sync_package_json

        pkg = {"dependencies": {}}
        pkg_path = tmp_path / "package.json"
        pkg_path.write_text(json.dumps(pkg))

        added = sync_package_json(["vitest", "eslint"], tmp_path)
        assert added == 2

        updated = json.loads(pkg_path.read_text())
        assert "vitest" in updated.get("devDependencies", {})
        assert "eslint" in updated.get("devDependencies", {})
