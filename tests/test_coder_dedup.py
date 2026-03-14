"""tests/test_coder_dedup.py — Tests for coder task deduplication logic."""
from __future__ import annotations

import pytest

from adelie.agents.coder_manager import (
    _tokenize,
    _find_duplicate_coder,
    _count_file_modifications,
)


class TestTokenize:
    def test_basic(self):
        assert "usechessgame" in _tokenize("Implement useChessGame hook")

    def test_removes_stop_words(self):
        tokens = _tokenize("Create the component for this feature")
        assert "the" not in tokens
        assert "for" not in tokens
        assert "feature" in tokens

    def test_empty_string(self):
        assert _tokenize("") == set()


class TestFindDuplicate:
    def test_exact_match(self):
        registry = {"coders": [{"layer": 0, "name": "foo", "last_task": "Build X"}]}
        assert _find_duplicate_coder(registry, 0, "foo", "Build X") == "foo"

    def test_similar_task(self):
        registry = {"coders": [{"layer": 0, "name": "chess_hook",
                     "last_task": "useChessGame hook logic"}]}
        result = _find_duplicate_coder(
            registry, 0, "game_hook_impl",
            "useChessGame hook game logic"
        )
        assert result == "chess_hook"

    def test_different_task(self):
        registry = {"coders": [{"layer": 0, "name": "chess_hook",
                     "last_task": "Implement chess game hook"}]}
        result = _find_duplicate_coder(
            registry, 0, "deploy_docker",
            "Deploy application to Docker container"
        )
        assert result is None

    def test_different_layer_no_match(self):
        registry = {"coders": [{"layer": 1, "name": "chess_hook",
                     "last_task": "Implement chess game hook"}]}
        result = _find_duplicate_coder(
            registry, 0, "chess_hook_v2",
            "Implement chess game hook"
        )
        assert result is None

    def test_empty_registry(self):
        registry = {"coders": []}
        result = _find_duplicate_coder(registry, 0, "new", "Build something")
        assert result is None

    def test_empty_task(self):
        registry = {"coders": [{"layer": 0, "name": "foo", "last_task": "Build X"}]}
        result = _find_duplicate_coder(registry, 0, "bar", "")
        assert result is None


class TestFileModificationCount:
    def test_counts_matching_files(self):
        registry = {"coders": [
            {"name": "a", "last_task": "Update Chessboard.tsx"},
            {"name": "b", "last_task": "Refactor Chessboard.tsx layout"},
            {"name": "c", "last_task": "Deploy server"},
        ]}
        assert _count_file_modifications(registry, ["src/Chessboard.tsx"]) == 2

    def test_no_matches(self):
        registry = {"coders": [
            {"name": "a", "last_task": "Deploy server"},
        ]}
        assert _count_file_modifications(registry, ["src/App.tsx"]) == 0

    def test_empty_files(self):
        registry = {"coders": [{"name": "a", "last_task": "Build X"}]}
        assert _count_file_modifications(registry, []) == 0

    def test_empty_registry(self):
        registry = {"coders": []}
        assert _count_file_modifications(registry, ["src/App.tsx"]) == 0
