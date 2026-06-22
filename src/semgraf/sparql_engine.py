"""SPARQL query execution wrapper around rdflib."""

from __future__ import annotations

import signal
from contextlib import contextmanager
from io import BytesIO
from typing import Any

from rdflib import Graph
from rdflib.query import Result

# Queries reused by the dedicated REST endpoints.

STATS_QUERY = """
SELECT ?pred (COUNT(*) AS ?cnt) WHERE {
    ?s ?pred ?o .
}
GROUP BY ?pred
ORDER BY DESC(?cnt)
"""

NODE_LABELS_QUERY = """
SELECT DISTINCT ?label WHERE {
    { ?uri rdfs:label ?label }
    UNION
    { ?uri skos:prefLabel ?label }
}
"""

NODE_TYPES_QUERY = """
SELECT DISTINCT ?type WHERE {
    ?uri rdf:type ?type .
}
"""

NODE_OUTGOING_QUERY = """
SELECT ?pred ?obj WHERE {
    ?uri ?pred ?obj .
}
ORDER BY ?pred
"""

NODE_INCOMING_QUERY = """
SELECT ?sub ?pred WHERE {
    ?sub ?pred ?uri .
}
ORDER BY ?pred
"""

SEARCH_QUERY = """
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

SELECT DISTINCT ?s ?label WHERE {
    { ?s rdfs:label ?label . FILTER(CONTAINS(LCASE(STR(?label)), LCASE("%(term)s"))) }
    UNION
    { ?s skos:prefLabel ?label . FILTER(CONTAINS(LCASE(STR(?label)), LCASE("%(term)s"))) }
    UNION
    { ?s skos:altLabel ?label . FILTER(CONTAINS(LCASE(STR(?label)), LCASE("%(term)s"))) }
}
LIMIT %(limit)d OFFSET %(offset)d
"""


class SparqlError(Exception):
    """Raised on SPARQL syntax errors or execution failures."""


class SparqlTimeout(Exception):
    """Raised when a query exceeds the timeout."""


@contextmanager
def _timeout(seconds: int):
    """Raise ``SparqlTimeout`` if execution exceeds *seconds*.

    If *seconds* is <= 0, the timeout fires immediately (useful for tests).

    Uses SIGALRM on the main thread; falls back to no timeout in
    threaded contexts (Flask dev server default).  This is acceptable
    for MVP — real timeout enforcement via a worker subprocess is a
    future improvement.
    """
    if seconds <= 0:
        raise SparqlTimeout(f"Query exceeded timeout of {seconds}s")

    def _handler(_signum, _frame):
        raise SparqlTimeout(f"Query exceeded timeout of {seconds}s")

    try:
        original = signal.signal(signal.SIGALRM, _handler)
    except ValueError:
        # Running in a non-main thread (Flask threaded mode) —
        # SIGALRM is unavailable.  Skip timeout enforcement.
        yield
        return

    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, original)


def execute_query(graph: Graph, query: str, timeout: int = 30) -> list[dict[str, Any]]:
    """Execute a SPARQL SELECT query and return results as a list of dicts.

    Args:
        graph: The rdflib Graph to query.
        query: A SPARQL SELECT query string.
        timeout: Maximum execution time in seconds (default 30).

    Returns:
        List of result bindings, where each binding is ``{var: value}``.

    Raises:
        SparqlError: If the query is syntactically invalid or execution fails.
        SparqlTimeout: If the query exceeds *timeout* seconds.
    """
    query = query.strip()
    if not query:
        raise SparqlError("Empty query")

    # Reject non-SELECT queries.  Look for the query form keyword
    # after stripping PREFIX/BASE declarations (which may span
    # multiple lines via Turtle-style line continuation).
    import re
    # Remove PREFIX/BASE lines (prefix name is like ``rdfs:``, hence ``\\S+``)
    cleaned = re.sub(
        r"(?im)^\s*(?:PREFIX|BASE)\s+\S+\s*<[^>]*>\s*\.?\s*",
        "",
        query,
    ).strip()
    if not cleaned.upper().startswith("SELECT"):
        raise SparqlError("Only SELECT queries are allowed in MVP")

    try:
        import rdflib.plugins.sparql  # noqa: F401 — ensure SPARQL engine loaded
    except ImportError:
        raise SparqlError("SPARQL engine not available (rdflib SPARQL plugin missing)")

    with _timeout(timeout):
        try:
            result: Result = graph.query(query)
        except Exception as exc:
            raise SparqlError(f"SPARQL syntax error: {exc}") from exc

    # Serialise to the standard SPARQL JSON results format.
    buf = BytesIO()
    try:
        result.serialize(format="json", destination=buf)
    except Exception as exc:
        raise SparqlError(f"Failed to serialise query results: {exc}") from exc

    import json
    data = json.loads(buf.getvalue())
    return data  # type: ignore[no-any-return]


def execute_query_raw(graph: Graph, query: str, timeout: int = 30) -> str:
    """Execute a SPARQL SELECT query and return raw JSON string.

    Args:
        graph: The rdflib Graph.
        query: SPARQL SELECT query.
        timeout: Seconds before timeout (default 30).

    Returns:
        Raw JSON result string (SPARQL 1.1 Query Results JSON Format).
    """
    data = execute_query(graph, query, timeout=timeout)
    import json
    return json.dumps(data, ensure_ascii=False)


def stats(graph: Graph) -> dict:
    """Return aggregate statistics about the graph."""
    triple_count = len(graph)
    subjects = set()
    objects = set()
    predicates = set()
    for s, p, o in graph:
        subjects.add(s)
        predicates.add(p)
        objects.add(o)

    return {
        "triple_count": triple_count,
        "subject_count": len(subjects),
        "predicate_count": len(predicates),
        "object_count": len(objects),
    }
