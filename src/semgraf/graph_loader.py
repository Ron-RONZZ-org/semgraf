"""Load Turtle file(s) into an rdflib.Graph with namespace bindings."""

from __future__ import annotations

from pathlib import Path

from rdflib import Graph
from rdflib.exceptions import ParserError as RdflibParserError


class GraphLoadError(Exception):
    """Raised when a Turtle file cannot be loaded."""


def load_ttl(path: Path) -> Graph:
    """Load a Turtle file into an rdflib.Graph.

    Args:
        path: Path to a .ttl file.

    Returns:
        An rdflib.Graph populated with the file's triples, with
        namespace bindings from the file preserved.

    Raises:
        GraphLoadError: If the file doesn't exist, can't be parsed,
            or contains no triples (warning only).
        FileNotFoundError: If *path* does not exist.
    """
    path = path.expanduser().resolve()

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    graph = Graph()

    try:
        graph.parse(source=str(path), format="turtle")
    except (RdflibParserError, Exception) as exc:
        # rdflib can raise various exceptions (BadSyntax, ParserError, etc.)
        # depending on the parser path. Catch broadly for a user-friendly error.
        raise GraphLoadError(
            f"Failed to parse Turtle file {path}: {exc}"
        ) from exc

    if len(graph) == 0:
        import warnings
        warnings.warn(f"File {path} contains no triples (empty graph)")

    return graph


def load_ttl_files(paths: list[Path]) -> Graph:
    """Load multiple Turtle files into a single rdflib.Graph.

    Args:
        paths: One or more file paths.

    Returns:
        A merged rdflib.Graph.
    """
    graph = Graph()
    for path in paths:
        g = load_ttl(path)
        graph += g
    return graph
