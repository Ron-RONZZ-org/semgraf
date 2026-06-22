"""Label resolution and URI prefix compression for RDF resources."""

from __future__ import annotations

from rdflib import Graph, URIRef, RDFS, SKOS, FOAF, DCTERMS, DC, RDF
from rdflib.namespace import NamespaceManager


# Label property candidates in priority order.
_LABEL_PREDICATES = [
    RDFS.label,
    SKOS.prefLabel,
    SKOS.altLabel,
    FOAF.name,
    DCTERMS.title,
    DC.title,
]


# Well-known prefix registrations (always available).
_BUILTIN_PREFIXES: dict[str, str] = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dct": "http://purl.org/dc/terms/",
    "dcterms": "http://purl.org/dc/terms/",
}


class PrefixMap:
    """Maps between namespace URIs and prefix:localname shorthand.

    Sources (priority order, later overrides earlier):
      1. Well-known prefixes (``_BUILTIN_PREFIXES``)
      2. Prefixes declared in the loaded Turtle file
      3. User-provided overrides (via CLI)
    """

    def __init__(self, graph: Graph | None = None, overrides: dict[str, str] | None = None):
        self._ns_to_prefix: dict[str, str] = {}
        self._prefix_to_ns: dict[str, str] = {}

        # 1. Well-known
        for prefix, ns in _BUILTIN_PREFIXES.items():
            self._register(prefix, ns)

        # 2. From graph
        if graph is not None:
            mgr: NamespaceManager = graph.namespace_manager
            for prefix, ns in mgr.namespaces():
                self._register(str(prefix), str(ns))

        # 3. User overrides
        if overrides:
            for prefix, ns in overrides.items():
                self._register(prefix, ns)

    def _register(self, prefix: str, ns: str) -> None:
        # Normalise but keep the trailing delimiter so that
        # ``uri[len(ns):]`` yields the clean local name.
        self._prefix_to_ns[prefix] = ns
        self._ns_to_prefix[ns] = prefix

    def compress(self, uri: str) -> str:
        """Return the shortest ``prefix:localname`` or the full URI."""
        if uri.startswith("_:"):
            return uri  # blank node — leave as-is
        for prefix, ns in sorted(self._prefix_to_ns.items(), key=lambda x: -len(x[1])):
            if uri.startswith(ns):
                local = uri[len(ns):]
                if local:
                    return f"{prefix}:{local}"
        return uri

    def expand(self, prefixed: str) -> str:
        """Expand a ``prefix:localname`` to a full URI (no-op if already a full URI)."""
        if ":" not in prefixed or prefixed.startswith("_"):
            return prefixed
        prefix, _, local = prefixed.partition(":")
        ns = self._prefix_to_ns.get(prefix)
        if ns is not None:
            return f"{ns}{local}"
        return prefixed


def resolve_label(graph: Graph, uri: str, prefix_map: PrefixMap | None = None) -> str:
    """Return the best human-readable label for a URI resource.

    Resolution chain (first match wins):
      1. ``rdfs:label`` with ``@en`` tag
      2. ``rdfs:label`` with no language tag
      3. ``rdfs:label`` with any language tag (alphabetically first)
      4. ``skos:prefLabel`` (same tag preference as above)
      5. ``skos:altLabel`` (same tag preference)
      6. ``foaf:name``, ``dcterms:title``, ``dc:title`` (same tag preference)
      7. Prefix-compressed URI via *prefix_map*
      8. Full URI (last resort)

    Args:
        graph: The rdflib Graph to search.
        uri: The resource URI.
        prefix_map: Optional PrefixMap for URI compression fallback.

    Returns:
        A human-readable label string.
    """
    if uri.startswith("_:"):
        # Blank node — abbreviate
        return uri[:12] + "…" if len(uri) > 12 else uri

    ref = URIRef(uri)

    for pred in _LABEL_PREDICATES:
        labels = list(graph.objects(subject=ref, predicate=pred))
        if not labels:
            continue
        label = _pick_best_label(labels)
        if label:
            return label

    # Fallback: prefix-compressed URI
    if prefix_map is not None:
        compressed = prefix_map.compress(uri)
        if compressed != uri:
            return compressed

    return uri  # last resort — full URI


def _pick_best_label(labels: list) -> str | None:
    """Pick the best label from a list of RDFLib Literals.

    Preference:
      1. ``@en`` or ``@en-*``
      2. No language tag
      3. Any other language tag (alphabetically first)
    """
    if not labels:
        return None

    en_label = None
    no_lang = None
    other: list[tuple[str, str]] = []

    for lit in labels:
        lang = (lit.language or "").lower()
        val = str(lit)
        if lang == "en" or lang.startswith("en-"):
            en_label = val
            break  # exact English match — short-circuit
        if not lang:
            no_lang = val
        else:
            other.append((lang, val))

    if en_label:
        return en_label
    if no_lang:
        return no_lang
    if other:
        other.sort(key=lambda x: x[0])
        return other[0][1]
    return str(labels[0])  # should not happen


def node_types(graph: Graph, uri: str, prefix_map: PrefixMap | None = None) -> list[str]:
    """Return ``rdf:type`` values for a resource as display strings."""
    ref = URIRef(uri)
    types = []
    for obj in graph.objects(subject=ref, predicate=RDF.type):
        label = resolve_label(graph, str(obj), prefix_map)
        compressed = prefix_map.compress(str(obj)) if prefix_map else str(obj)
        types.append(compressed if label == str(obj) else label)
    return types
