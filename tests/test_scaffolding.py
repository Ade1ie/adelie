"""tests/test_scaffolding.py — Tests for project scaffolding detection."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest


@pytest.fixture
def tmp_project(tmp_path, monkeypatch):
    """Set up a temporary project directory."""
    import adelie.config as cfg
    ws = tmp_path / ".adelie" / "kb"
    ws.mkdir(parents=True)
    monkeypatch.setattr(cfg, "WORKSPACE_PATH", ws)
    monkeypatch.setattr(cfg, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cfg, "ADELIE_ROOT", tmp_path / ".adelie")
    return tmp_path


class TestScaffoldingNeed:
    def test_detects_missing_react_files(self, tmp_project):
        """React/Vite project without entry files triggers scaffolding."""
        # Create a .tsx file to trigger React detection
        src = tmp_project / "src"
        src.mkdir()
        (src / "App.tsx").write_text("export default function App() {}")

        from adelie.agents.expert_ai import _get_scaffolding_need
        result = _get_scaffolding_need()

        assert "SCAFFOLDING NOTE" in result
        assert "index.html" in result
        assert "package.json" in result
        assert "tsconfig.json" in result
        assert "src/main.tsx" in result

    def test_no_scaffolding_when_complete(self, tmp_project):
        """Complete project returns empty string."""
        src = tmp_project / "src"
        src.mkdir()
        (src / "App.tsx").write_text("export default function App() {}")
        (src / "main.tsx").write_text("ReactDOM.createRoot()")
        (tmp_project / "index.html").write_text("<html></html>")
        (tmp_project / "package.json").write_text("{}")
        (tmp_project / "tsconfig.json").write_text("{}")
        (tmp_project / "vite.config.ts").write_text("export default {}")

        from adelie.agents.expert_ai import _get_scaffolding_need
        result = _get_scaffolding_need()

        assert result == ""

    def test_python_project_detection(self, tmp_project):
        """Python project without requirements.txt triggers scaffolding."""
        (tmp_project / "main.py").write_text("print('hello')")

        from adelie.agents.expert_ai import _get_scaffolding_need
        result = _get_scaffolding_need()

        assert "requirements.txt" in result

    def test_empty_project_no_detection(self, tmp_project):
        """Empty project returns nothing — no files to detect type from."""
        from adelie.agents.expert_ai import _get_scaffolding_need
        result = _get_scaffolding_need()

        assert result == ""

    def test_detects_missing_tsconfig_references(self, tmp_project):
        """tsconfig.json referencing nonexistent tsconfig.node.json is caught."""
        import json
        src = tmp_project / "src"
        src.mkdir()
        (src / "App.tsx").write_text("export default function App() {}")
        (src / "main.tsx").write_text("ReactDOM.createRoot()")
        (tmp_project / "index.html").write_text("<html></html>")
        (tmp_project / "package.json").write_text(json.dumps({"dependencies": {}}))
        (tmp_project / "vite.config.ts").write_text("export default {}")
        (tmp_project / "tsconfig.json").write_text(json.dumps({
            "compilerOptions": {},
            "references": [{"path": "./tsconfig.node.json"}]
        }))

        from adelie.agents.expert_ai import _get_scaffolding_need
        result = _get_scaffolding_need()

        assert "tsconfig.node.json" in result
        assert "TS6053" in result

    def test_detects_missing_types_packages(self, tmp_project):
        """tsconfig types: ['node'] without @types/node is caught."""
        import json
        src = tmp_project / "src"
        src.mkdir()
        (src / "App.tsx").write_text("export default function App() {}")
        (src / "main.tsx").write_text("ReactDOM.createRoot()")
        (tmp_project / "index.html").write_text("<html></html>")
        (tmp_project / "package.json").write_text(json.dumps({"dependencies": {}}))
        (tmp_project / "vite.config.ts").write_text("export default {}")
        (tmp_project / "tsconfig.json").write_text(json.dumps({
            "compilerOptions": {"types": ["node"]}
        }))

        from adelie.agents.expert_ai import _get_scaffolding_need
        result = _get_scaffolding_need()

        assert "@types/node" in result
        assert "TS2688" in result
