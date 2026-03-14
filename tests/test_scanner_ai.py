"""tests/test_scanner_ai.py — Tests for Scanner AI."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest


MOCK_SCAN_RESPONSE = [
    {
        "category": "skills",
        "filename": "architecture.md",
        "tags": ["architecture"],
        "summary": "System architecture",
        "content": "# Architecture\n\n## Overview\nThis is a Next.js app.",
    },
    {
        "category": "dependencies",
        "filename": "tech_stack.md",
        "tags": ["tech"],
        "summary": "Tech stack",
        "content": "# Tech Stack\n\n- JavaScript\n- React",
    },
]


@pytest.fixture
def tmp_project(tmp_path, monkeypatch):
    """Create a fake project with source files."""
    import adelie.config as cfg
    import adelie.kb.retriever as r

    ws = tmp_path / ".adelie" / "workspace"
    ws.mkdir(parents=True)
    monkeypatch.setattr(cfg, "WORKSPACE_PATH", ws)
    monkeypatch.setattr(r, "WORKSPACE_PATH", ws)
    monkeypatch.setattr(r, "INDEX_FILE", ws / "index.json")
    r.ensure_workspace()

    # Create source files
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.js").write_text("export default function App() { return <div>Hello</div>; }", encoding="utf-8")
    (tmp_path / "src" / "api").mkdir()
    (tmp_path / "src" / "api" / "auth.py").write_text("def login(): pass", encoding="utf-8")
    (tmp_path / "src" / "api" / "users.py").write_text("def get_users(): pass", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"name": "test-app", "dependencies": {"react": "^18"}}', encoding="utf-8")

    return tmp_path


class TestScannerAI:
    def test_scan_project_collects_files(self, tmp_project):
        from adelie.agents.scanner_ai import _scan_project
        result = _scan_project(tmp_project)
        assert result["total_files"] >= 3
        assert len(result["configs"]) >= 1  # package.json
        assert "test-app" in result["configs"][0]

    def test_run_scan_writes_kb_docs(self, tmp_project, monkeypatch):
        import adelie.agents.scanner_ai as s
        import adelie.kb.retriever as r

        monkeypatch.setattr(s, "WORKSPACE_PATH", tmp_project / ".adelie" / "workspace")

        with patch("adelie.agents.scanner_ai.generate") as mock_gen:
            mock_gen.return_value = json.dumps(MOCK_SCAN_RESPONSE)
            written = s.run_scan(
                project_root=tmp_project,
                workspace_path=tmp_project / ".adelie" / "workspace",
            )

        assert len(written) == 2
        assert (tmp_project / ".adelie" / "workspace" / "skills" / "architecture.md").exists()
        assert (tmp_project / ".adelie" / "workspace" / "dependencies" / "tech_stack.md").exists()

    def test_auto_assign_coders(self, tmp_project, monkeypatch):
        import adelie.agents.scanner_ai as s
        import adelie.agents.coder_ai as c

        coder_root = tmp_project / ".adelie" / "coder"
        monkeypatch.setattr(c, "CODER_ROOT", coder_root)
        monkeypatch.setattr(s, "WORKSPACE_PATH", tmp_project / ".adelie" / "workspace")

        # Mock coder_manager registry functions
        with patch("adelie.agents.scanner_ai.auto_assign_coders.__module__", "adelie.agents.scanner_ai"):
            coders = s.auto_assign_coders(tmp_project)

        # Should have at least Layer 1 coder for "src"
        assert len(coders) >= 1
        layer1_names = [c["name"] for c in coders if c["layer"] == 1]
        assert "src" in layer1_names

    def test_sanitize_coder_name(self):
        from adelie.agents.scanner_ai import _sanitize_coder_name
        assert _sanitize_coder_name("src") == "src"
        assert _sanitize_coder_name("my-app") == "my_app"
        assert _sanitize_coder_name("Backend API") == "backend_api"

    def test_empty_project_returns_empty(self, tmp_path, monkeypatch):
        import adelie.config as cfg
        import adelie.agents.scanner_ai as s

        ws = tmp_path / ".adelie" / "workspace"
        ws.mkdir(parents=True)
        monkeypatch.setattr(cfg, "WORKSPACE_PATH", ws)
        monkeypatch.setattr(s, "WORKSPACE_PATH", ws)

        result = s.run_scan(project_root=tmp_path, workspace_path=ws)
        assert result == []
