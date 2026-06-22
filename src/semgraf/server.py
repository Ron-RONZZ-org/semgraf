"""Flask application factory and route definitions."""

from __future__ import annotations

import json
import urllib.parse
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, request, send_from_directory

from rdflib import Graph, URIRef, RDF

from semgraf.graph_loader import GraphLoadError
from semgraf.label_utils import PrefixMap, node_types, resolve_label
from semgraf.sparql_engine import (
    NODE_INCOMING_QUERY,
    NODE_OUTGOING_QUERY,
    SEARCH_QUERY,
    SparqlError,
    SparqlTimeout,
    execute_query,
    stats,
)

HERE = Path(__file__).resolve().parent
STATIC_DIR = HERE / "static"

# Page size for node-detail pagination.
_PAGE_SIZE = 50


def create_app(graph: Graph, prefix_map: PrefixMap | None = None) -> Flask:
    """Create and configure the Flask application.

    Args:
        graph: An rdflib.Graph loaded with Turtle data.
        prefix_map: A PrefixMap for URI compression (created from *graph* if None).

    Returns:
        A configured Flask app.
    """
    app = Flask(__name__, static_folder=None)

    if prefix_map is None:
        prefix_map = PrefixMap(graph)

    # Store shared state in app config (Flask's app context).
    app.config["graph"] = graph
    app.config["prefix_map"] = prefix_map

    # ------------------------------------------------------------------ /
    @app.route("/")
    def index():
        return send_from_directory(str(STATIC_DIR), "index.html")

    # ------------------------------------------------------------- /api/stats
    @app.route("/api/stats")
    def api_stats():
        g: Graph = app.config["graph"]
        pm: PrefixMap = app.config["prefix_map"]
        s = stats(g)

        # Build predicate list with labels, sorted by count descending.
        pred_rows = []
        seen: set[str] = set()
        for s_node, p_node, _o_node in g:
            p_uri = str(p_node)
            if p_uri not in seen:
                seen.add(p_uri)
                cnt = len(list(g.triples((None, p_node, None))))
                pred_rows.append({
                    "uri": p_uri,
                    "label": pm.compress(p_uri),
                    "count": cnt,
                })
        pred_rows.sort(key=lambda x: -x["count"])

        # Namespace bindings.
        ns = dict(pm._prefix_to_ns)  # type: ignore[arg-type]

        return jsonify({
            "triple_count": s["triple_count"],
            "subject_count": s["subject_count"],
            "predicate_count": s["predicate_count"],
            "object_count": s["object_count"],
            "predicates": pred_rows,
            "namespaces": ns,
        })

    # ---------------------------------------------------------- /api/sparql
    @app.route("/api/sparql")
    def api_sparql():
        g: Graph = app.config["graph"]
        query = request.args.get("query", "").strip()
        if not query:
            return jsonify({"error": "Missing 'query' parameter"}), 400

        try:
            data = execute_query(g, query)
        except SparqlError as exc:
            return jsonify({"error": str(exc), "query": query}), 400
        except SparqlTimeout as exc:
            return jsonify({"error": str(exc), "query": query}), 408

        return jsonify(data)

    # ------------------------------------------------------------ /api/node
    @app.route("/api/node")
    def api_node():
        g: Graph = app.config["graph"]
        pm: PrefixMap = app.config["prefix_map"]

        uri = request.args.get("uri", "")
        if not uri:
            return jsonify({"error": "Missing 'uri' parameter"}), 400

        ref = URIRef(uri)
        if (ref, None, None) not in g and (None, None, ref) not in g:
            return jsonify({"error": "Node not found in graph", "uri": uri}), 404

        limit = _int_param(request, "limit", _PAGE_SIZE)
        offset = _int_param(request, "offset", 0)

        label = resolve_label(g, uri, pm)
        labels = _collect_labels(g, uri)
        types = node_types(g, uri, pm)

        # Outgoing triples (subject = uri)
        outgoing_raw = list(g.triples((ref, None, None)))
        outgoing = _serialise_triples(g, pm, outgoing_raw, "object")
        outgoing_total = len(outgoing)
        outgoing_page = outgoing[offset:offset + limit]

        # Incoming triples (object = uri)
        incoming_raw = list(g.triples((None, None, ref)))
        incoming = _serialise_triples(g, pm, incoming_raw, "subject")
        incoming_total = len(incoming)
        incoming_page = incoming[offset:offset + limit]

        return jsonify({
            "uri": uri,
            "label": label,
            "labels": labels,
            "types": types,
            "properties": _build_properties(g, pm, uri),
            "outgoing": {
                "items": outgoing_page,
                "total": outgoing_total,
                "limit": limit,
                "offset": offset,
            },
            "incoming": {
                "items": incoming_page,
                "total": incoming_total,
                "limit": limit,
                "offset": offset,
            },
        })

    # ----------------------------------------------------------- /api/search
    @app.route("/api/search")
    def api_search():
        g: Graph = app.config["graph"]
        pm: PrefixMap = app.config["prefix_map"]

        q = request.args.get("q", "").strip()
        if not q:
            return jsonify({"results": [], "total": 0, "limit": 0, "offset": 0})

        limit = _int_param(request, "limit", 50)
        offset = _int_param(request, "offset", 0)

        # Use SPARQL CONTAINS for case-insensitive substring search.
        sparql_query = SEARCH_QUERY % {
            "term": _escape_sparql_string(q),
            "limit": limit,
            "offset": offset,
        }

        try:
            raw = execute_query(g, sparql_query)
        except SparqlError:
            return jsonify({"results": [], "total": 0, "limit": limit, "offset": offset})

        results = []
        # raw is SPARQL JSON results format
        bindings = raw.get("results", {}).get("bindings", [])
        seen_uris: set[str] = set()
        for b in bindings:
            s_uri = b.get("s", {}).get("value", "")
            label = b.get("label", {}).get("value", "")
            if s_uri and s_uri not in seen_uris:
                seen_uris.add(s_uri)
                results.append({
                    "uri": s_uri,
                    "label": label or pm.compress(s_uri),
                    "types": node_types(g, s_uri, pm),
                })

        return jsonify({
            "results": results,
            "total": len(results),
            "limit": limit,
            "offset": offset,
        })

    return app


# ------------------------------------------------------------------ helpers


def _int_param(request, name: str, default: int) -> int:
    """Parse an integer query parameter with a fallback default."""
    val = request.args.get(name, "")
    if val.isdigit():
        return int(val)
    return default


def _escape_sparql_string(s: str) -> str:
    """Escape a string literal for safe embedding in a SPARQL query."""
    return s.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')


def _collect_labels(graph: Graph, uri: str) -> list[str]:
    """Collect all rdfs:label / skos:prefLabel literals for a URI."""
    from rdflib import RDFS, SKOS, Literal
    ref = URIRef(uri)
    labels: list[str] = []
    for pred in (RDFS.label, SKOS.prefLabel, SKOS.altLabel):
        for obj in graph.objects(subject=ref, predicate=pred):
            lit: Literal = obj
            lang = lit.language or ""
            label_str = str(lit)
            if lang:
                labels.append(f"{label_str} [{lang}]")
            else:
                labels.append(label_str)
    return labels


def _serialise_triples(
    graph: Graph,
    pm: PrefixMap,
    triples: list,
    target_key: str,
) -> list[dict]:
    """Turn raw rdflib triples into serialisable dicts.

    *target_key* is either ``"object"`` (for outgoing) or ``"subject"``
    (for incoming).
    """
    items = []
    for s, p, o in triples:
        pred = {"uri": str(p), "label": pm.compress(str(p))}
        if target_key == "object":
            target = _value_dict(graph, pm, o)
            items.append({"predicate": pred, "object": target})
        else:
            target = _value_dict(graph, pm, s)
            items.append({"subject": target, "predicate": pred})
    return items


def _value_dict(graph: Graph, pm: PrefixMap, term) -> dict:
    """Turn an rdflib term (URIRef or Literal) into a display dict."""
    from rdflib import Literal, URIRef
    if isinstance(term, URIRef):
        uri = str(term)
        return {
            "uri": uri,
            "label": resolve_label(graph, uri, pm),
            "type": "uri",
        }
    elif isinstance(term, Literal):
        d: dict[str, Any] = {"value": str(term), "type": "literal"}
        if term.language:
            d["lang"] = term.language
        if term.datatype:
            from rdflib import XSD
            d["datatype"] = pm.compress(str(term.datatype)) if pm else str(term.datatype)
        return d
    else:
        return {"value": str(term), "type": "unknown"}


def _build_properties(graph: Graph, pm: PrefixMap, uri: str) -> list[dict]:
    """Group outgoing triples by predicate (excluding label properties)."""
    from rdflib import RDFS, SKOS, Literal, URIRef
    ref = URIRef(uri)
    skip_preds = {RDFS.label, SKOS.prefLabel, SKOS.altLabel}
    groups: dict[str, dict] = {}

    for _s, p, o in graph.triples((ref, None, None)):
        p_uri = str(p)
        if p_uri in skip_preds:
            continue
        if p_uri not in groups:
            groups[p_uri] = {
                "predicate": {"uri": p_uri, "label": pm.compress(p_uri)},
                "objects": [],
            }
        groups[p_uri]["objects"].append(_value_dict(graph, pm, o))

    return list(groups.values())
