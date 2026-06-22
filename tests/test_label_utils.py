"""Tests for label_utils.py."""

from __future__ import annotations

import pytest
from semgraf.label_utils import PrefixMap, resolve_label, node_types
from rdflib import Graph, URIRef


SAMPLE_TTL = """
@prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix foaf: <http://xmlns.com/foaf/0.1/> .
@prefix :     <http://example.org/> .

:Alice  a :Person ;
    rdfs:label "Alice"@en , "Alico"@eo ;
    foaf:knows :Bob .

:Bob  a :Person ;
    rdfs:label "Bob"@en .

:NoLabel  a :Person .

:Person  a rdfs:Class ;
    rdfs:label "Person"@en , "Person" .
"""


@pytest.fixture
def graph():
    g = Graph()
    g.parse(data=SAMPLE_TTL, format="turtle")
    return g


@pytest.fixture
def prefix_map(graph):
    return PrefixMap(graph)


class TestResolveLabel:
    def test_en_label_preferred(self, graph, prefix_map):
        label = resolve_label(graph, "http://example.org/Alice", prefix_map)
        assert label == "Alice"

    def test_no_lang_label_fallback(self, graph, prefix_map):
        label = resolve_label(graph, "http://example.org/Person", prefix_map)
        assert label == "Person"

    def test_uri_fallback_when_no_label(self, graph, prefix_map):
        label = resolve_label(graph, "http://example.org/NoLabel", prefix_map)
        # Falls back to prefix-compressed URI
        assert "NoLabel" in label

    def test_unknown_uri_full_uri(self, graph, prefix_map):
        label = resolve_label(graph, "http://nonexistent.org/foo", prefix_map)
        assert label == "http://nonexistent.org/foo"

    def test_blank_node(self, graph, prefix_map):
        label = resolve_label(graph, "_:abc123xyz789", prefix_map)
        assert label.startswith("_:abc123")


class TestPrefixMap:
    def test_compress_known_prefix(self, prefix_map):
        result = prefix_map.compress("http://xmlns.com/foaf/0.1/Person")
        assert result == "foaf:Person"

    def test_compress_unknown_prefix(self, prefix_map):
        uri = "http://custom.example.org/resource"
        result = prefix_map.compress(uri)
        assert result == uri

    def test_compress_blank_node(self, prefix_map):
        assert prefix_map.compress("_:blank1") == "_:blank1"

    def test_expand_known(self, prefix_map):
        assert prefix_map.expand("foaf:Person") == "http://xmlns.com/foaf/0.1/Person"

    def test_expand_unknown(self, prefix_map):
        assert prefix_map.expand("unknown:foo") == "unknown:foo"

    def test_builtin_prefixes_always_available(self):
        pm = PrefixMap()
        assert pm.compress("http://www.w3.org/2001/XMLSchema#string") == "xsd:string"


class TestNodeTypes:
    def test_node_types(self, graph, prefix_map):
        types = node_types(graph, "http://example.org/Alice", prefix_map)
        assert len(types) >= 1


