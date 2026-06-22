"""Tests for graph_loader.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from semgraf.graph_loader import GraphLoadError, load_ttl, load_ttl_files


class TestLoadTtl:
    def test_load_valid_file(self, sample_ttl):
        graph = load_ttl(Path(sample_ttl))
        assert len(graph) > 0

    def test_load_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_ttl(Path("/nonexistent/file.ttl"))

    def test_load_invalid_file(self, tmp_path):
        bad = tmp_path / "bad.ttl"
        bad.write_text("this is not valid turtle @@@")
        with pytest.raises(GraphLoadError):
            load_ttl(bad)

    def test_load_empty_ttl(self, empty_ttl):
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            graph = load_ttl(Path(empty_ttl))
            assert len(graph) == 0
            assert len(w) >= 1
            assert "no triples" in str(w[0].message).lower()


class TestLoadTtlFiles:
    def test_multiple_files(self, sample_ttl, empty_ttl):
        graph = load_ttl_files([Path(sample_ttl), Path(empty_ttl)])
        assert len(graph) > 0

    def test_single_file(self, sample_ttl):
        graph = load_ttl_files([Path(sample_ttl)])
        assert len(graph) > 0
