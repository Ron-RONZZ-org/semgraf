"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
from rdflib import Graph

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def sample_ttl() -> str:
    """Path to a sample Turtle file with diverse RDF constructs."""
    return str(FIXTURE_DIR / "sample.ttl")


@pytest.fixture
def empty_ttl() -> str:
    """Path to a Turtle file with no triples."""
    return str(FIXTURE_DIR / "empty.ttl")


@pytest.fixture
def sample_graph() -> Graph:
    """An rdflib.Graph pre-loaded with sample data."""
    g = Graph()
    g.parse(source=str(FIXTURE_DIR / "sample.ttl"), format="turtle")
    return g


@pytest.fixture
def empty_graph() -> Graph:
    """An empty rdflib.Graph."""
    return Graph()
