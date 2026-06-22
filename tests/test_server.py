"""Tests for server.py — Flask routes."""

from __future__ import annotations

import json

import pytest
from rdflib import Graph

from semgraf.label_utils import PrefixMap
from semgraf.server import create_app


@pytest.fixture
def client(sample_graph):
    pm = PrefixMap(sample_graph)
    app = create_app(sample_graph, prefix_map=pm)
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def empty_client(empty_graph):
    pm = PrefixMap(empty_graph)
    app = create_app(empty_graph, prefix_map=pm)
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestIndex:
    def test_index_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.content_type.startswith("text/html")


class TestStats:
    def test_stats_non_empty(self, client):
        resp = client.get("/api/stats")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["triple_count"] > 0
        assert "predicates" in data
        assert "namespaces" in data

    def test_stats_empty(self, empty_client):
        resp = empty_client.get("/api/stats")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["triple_count"] == 0


class TestSparql:
    def test_valid_query(self, client):
        resp = client.get(
            "/api/sparql?query=" + _q("SELECT ?s WHERE { ?s a ?o } LIMIT 5")
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "results" in data

    def test_missing_query(self, client):
        resp = client.get("/api/sparql")
        assert resp.status_code == 400

    def test_invalid_query(self, client):
        resp = client.get("/api/sparql?query=" + _q("SELECT ???"))
        assert resp.status_code == 400

    def test_non_select_query(self, client):
        resp = client.get("/api/sparql?query=" + _q("INSERT DATA { }"))
        assert resp.status_code == 400


class TestNode:
    def test_existing_node(self, client):
        resp = client.get(
            "/api/node?uri=" + _q("http://example.org/Alice")
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["label"] == "Alice"
        assert "outgoing" in data
        assert "incoming" in data

    def test_nonexistent_node(self, client):
        resp = client.get(
            "/api/node?uri=" + _q("http://example.org/Nobody")
        )
        assert resp.status_code == 404

    def test_missing_uri(self, client):
        resp = client.get("/api/node")
        assert resp.status_code == 400

    def test_node_with_types(self, client):
        resp = client.get(
            "/api/node?uri=" + _q("http://example.org/Alice")
        )
        data = json.loads(resp.data)
        assert len(data["types"]) > 0


class TestSearch:
    def test_search_finds_node(self, client):
        resp = client.get("/api/search?q=Alice")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data["results"]) >= 1
        assert any("Alice" in r["label"] for r in data["results"])

    def test_search_no_match(self, client):
        resp = client.get("/api/search?q=XYZZY")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data["results"]) == 0

    def test_search_empty_query(self, client):
        resp = client.get("/api/search?q=")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data["results"]) == 0

    def test_search_case_insensitive(self, client):
        resp = client.get("/api/search?q=alice")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data["results"]) >= 1


def _q(s):
    import urllib.parse
    return urllib.parse.quote(s)
