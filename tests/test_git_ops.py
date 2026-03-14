"""tests/test_git_ops.py — Tests for Git integration utilities."""
from __future__ import annotations

import subprocess

import pytest


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repository."""
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), capture_output=True)
    # Create initial commit
    (tmp_path / "README.md").write_text("# Test", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=str(tmp_path), capture_output=True)
    return tmp_path


class TestGitOps:
    def test_is_git_repo(self, git_repo, tmp_path):
        from adelie.git_ops import is_git_repo
        assert is_git_repo(git_repo) is True
        assert is_git_repo(tmp_path / "nonexistent") is False

    def test_get_status_clean(self, git_repo):
        from adelie.git_ops import get_status
        status = get_status(git_repo)
        assert status["ok"] is True
        assert status["changed_files"] == 0

    def test_get_status_dirty(self, git_repo):
        from adelie.git_ops import get_status
        (git_repo / "new_file.txt").write_text("hello", encoding="utf-8")
        status = get_status(git_repo)
        assert status["ok"] is True
        assert status["changed_files"] > 0

    def test_auto_commit(self, git_repo):
        from adelie.git_ops import auto_commit
        (git_repo / "src.py").write_text("print('hello')", encoding="utf-8")
        result = auto_commit("test commit", files=["src.py"], root=git_repo)
        assert result["ok"] is True
        assert result["committed"] is True
        assert result["files_count"] == 1

    def test_auto_commit_nothing(self, git_repo):
        from adelie.git_ops import auto_commit
        result = auto_commit("empty commit", root=git_repo)
        assert result["ok"] is True
        assert result["committed"] is False

    def test_auto_commit_not_git(self, tmp_path):
        from adelie.git_ops import auto_commit
        result = auto_commit("test", root=tmp_path)
        assert result["ok"] is False

    def test_get_log(self, git_repo):
        from adelie.git_ops import get_log
        log = get_log(n=5, root=git_repo)
        assert len(log) == 1
        assert log[0]["message"] == "initial"

    def test_auto_push_no_remote(self, git_repo):
        from adelie.git_ops import auto_push
        result = auto_push(root=git_repo)
        assert result["ok"] is False  # No remote configured
