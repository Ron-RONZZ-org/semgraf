"""Tests for sparql_engine.py."""

from __future__ import annotations

import pytest

from semgraf.sparql_engine import (
    SparqlError,
    SparqlTimeout,
    execute_query,
    stats,
)


class TestExecuteQuery:
    def test_select_all(self, sample_graph):
        data = execute_query(sample_graph, "SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 10")
        assert "results" in data
        assert len(data["results"]["bindings"]) <= 10

    def test_specific_query(self, sample_graph):
        data = execute_query(
            sample_graph,
            'SELECT ?label WHERE { <http://example.org/Alice> rdfs:label ?label }',
        )
        bindings = data["results"]["bindings"]
        assert len(bindings) >= 1

    def test_empty_query_raises(self, sample_graph):
        with pytest.raises(SparqlError, match="Empty query"):
            execute_query(sample_graph, "   ")

    def test_non_select_query_raises(self, sample_graph):
        with pytest.raises(SparqlError, match="Only SELECT"):
            execute_query(sample_graph, "INSERT DATA { <> a <> }")

    def test_malformed_query(self, sample_graph):
        with pytest.raises(SparqlError):
            execute_query(sample_graph, "SELECT * WHERE { ??? }")

    def test_empty_graph(self, empty_graph):
        data = execute_query(empty_graph, "SELECT ?s ?p ?o WHERE { ?s ?p ?o }")
        assert len(data["results"]["bindings"]) == 0

    def test_query_timeout(self, sample_graph):
        # Timeout a query that is intentionally slow
        with pytest.raises(SparqlTimeout):
            execute_query(
                sample_graph,
                "SELECT ?s ?p ?o WHERE { ?s ?p ?o . ?s1 ?p1 ?o1 }",
                timeout=0,
            )


class TestStats:
    def test_stats_non_empty(self, sample_graph):
        s = stats(sample_graph)
        assert s["triple_count"] > 0
        assert s["subject_count"] > 0
        assert s["predicate_count"] > 0

    def test_stats_empty(self, empty_graph):
        s = stats(empty_graph)
        assert s["triple_count"] == 0
        assert s["subject_count"] == 0
        assert s["predicate_count"] == 0

    def test_stats_types(self, sample_graph):
        s = stats(sample_graph)
        assert isinstance(s["triple_count"], int)
        assert isinstance(s["subject_count"], int)
        assert isinstance(s["predicate_count"], int)



