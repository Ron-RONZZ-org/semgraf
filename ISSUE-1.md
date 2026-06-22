---
title: "Architecture Design & File Plan for semgraf MVP"
labels: ["architecture", "design-doc", "mvp"]
assignees: []
---

# Architecture Design: semgraf (semantika grafio)

## 1. Architecture Overview

### High-Level Components

```
┌──────────────┐     Turtle .ttl     ┌──────────────────┐
│  Turtle File │ ──────────────────> │  graph_loader.py  │
│   (on disk)  │                     │  (rdflib.Graph)   │
└──────────────┘                     └────────┬─────────┘
                                              │ rdflib Graph
                                              ▼
┌──────────────┐     HTTP JSON      ┌──────────────────┐
│   Browser    │ <────────────────> │    server.py      │
│  (vis.js)    │     REST API       │   (Flask)         │
│              │                    │                   │
│  index.html  │                    │  ┌─────────────┐  │
│  graph.js    │                    │  │sparql_engine│  │
│  style.css   │                    │  │  .py        │  │
└──────────────┘                    │  └──────┬──────┘  │
                                    │         │ rdflib  │
                                    │         │ SPARQL  │
                                    │         ▼         │
                                    │  rdflib.Graph     │
                                    │  (in-memory)      │
                                    └──────────────────┘
```

### Data Flow

1. **Startup**: CLI parses args → `graph_loader.py` loads Turtle file(s) into an `rdflib.Graph` (in-memory)
2. **Serving**: Flask server starts with the loaded Graph in application context
3. **Request**: Browser makes REST calls to the server
4. **Response**: Server routes requests → `sparql_engine.py` executes SPARQL queries against the in-memory Graph → serializes results as JSON
5. **Rendering**: vis.js in the browser renders the returned graph data

### Separation of Concerns

| Layer | Module | Responsibility |
|-------|--------|----------------|
| CLI | `cli.py` | Argument parsing, wiring components together |
| Data | `graph_loader.py` | File I/O, Turtle parsing, validation, access to the rdflib Graph |
| Query | `sparql_engine.py` | SPARQL execution, result formatting, timeout enforcement |
| API | `server.py` | HTTP routing, request handling, response serialization |
| View | `static/` | Browser-side UI: graph visualization, search, entity inspection |

## 2. File Plan (Refined)

```
semgraf/
├── src/semgraf/
│   ├── __init__.py              # Version string, clean public exports
│   ├── __main__.py              # `python -m semgraf` → calls cli.main()
│   ├── cli.py                   # Argument parser: --port, --host, --ttl path(s), optional --prefix-map
│   ├── server.py                # Flask app factory, route definitions, static file serving
│   ├── graph_loader.py          # Load Turtle file(s) → rdflib.Graph, validate, store namespace bindings
│   ├── sparql_engine.py         # Query() wrapper: execute SPARQL, handle errors, format JSON results
│   ├── label_utils.py           # Label resolution (rdfs:label, skos:prefLabel, fallback), prefix compression
│   └── static/
│       ├── index.html           # Single-page application shell
│       ├── app.js               # All frontend logic: search, graph rendering, entity panel, SPARQL input
│       └── style.css            # Minimal styling (~200 lines)
├── tests/
│   ├── test_graph_loader.py     # Fixtures: valid Turtle, invalid Turtle, empty graph, blank nodes
│   ├── test_sparql_engine.py    # Query execution, error handling, result format
│   └── test_server.py           # HTTP-level tests (Flask test client)
├── pyproject.toml               # Build config: dependencies, entry points, project metadata
├── LICENSE                      # AGPL-3.0 (already exists)
└── README.md                    # Quickstart, example, CLI reference
```

### Rationale for Changes vs. Original Proposal

| Change | Why |
|--------|-----|
| Split `graph.js` → `app.js` only | One JS file is simpler for MVP; no module bundler needed |
| Added `label_utils.py` | Label resolution logic is nontrivial (language tags, fallback chain) and deserves its own module |
| Added `tests/` | Essential for a maintainable project — even MVP needs test coverage |
| Added `__main__.py` | Standard Python convention for `python -m semgraf` |
| Removed separate `sparql-client.js` | Keep all JS in `app.js` for MVP; split when complexity demands it |

**Not needed for MVP** (do not create):
- `Dockerfile` — local-first means `pip install` is the primary distribution
- `setup.py` / `setup.cfg` — `pyproject.toml` is sufficient
- `Makefile` — `semgraf` CLI is the interface
- Config file support — CLI flags are enough for MVP
- CSS framework (Bootstrap, Tailwind) — custom minimal CSS keeps dependencies zero

## 3. API Design

### Endpoints

#### `GET /`
Serves `static/index.html`.

#### `GET /api/stats`
Returns an overview of the loaded graph.

**Response** `200 OK`:
```json
{
  "triple_count": 15234,
  "subject_count": 3421,
  "predicate_count": 87,
  "object_count": 5126,
  "predicates": [
    {"uri": "http://www.w3.org/1999/02/22-rdf-syntax-ns#type", "label": "rdf:type", "count": 4500},
    {"uri": "http://www.w3.org/2000/01/rdf-schema#label", "label": "rdfs:label", "count": 3400}
  ],
  "namespaces": {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "foaf": "http://xmlns.com/foaf/0.1/"
  }
}
```

- `predicates` sorted by count descending
- `label` uses prefix compression for display

#### `GET /api/sparql?query=...`
SPARQL query proxy. Accepts URL-encoded SPARQL query string.

**Response** `200 OK`: [SPARQL 1.1 Query Results JSON Format](https://www.w3.org/TR/sparql11-results-json/) (standard W3C format, produced directly by rdflib's `results.serialize(format='json')`)

**Response** `400 Bad Request`:
```json
{"error": "SPARQL syntax error: ...", "query": "SELECT ..."}
```

**Response** `408 Request Timeout`:
```json
{"error": "Query exceeded timeout of 30s", "query": "SELECT ..."}
```

**Security note**: Since this is a local-first tool (localhost-only by default), SPARQL injection is a low-risk concern, but we still validate and reject non-SELECT queries in MVP (no DELETE/INSERT/UPDATE allowed).

#### `GET /api/node?uri=<url-encoded-URI>`
Details about a specific node (subject or object resource).

**Response** `200 OK`:
```json
{
  "uri": "http://xmlns.com/foaf/0.1/Person",
  "label": "foaf:Person",
  "labels": ["Person", "Persona"],
  "types": ["http://www.w3.org/2002/07/owl#Class"],
  "properties": [
    {"predicate": {"uri": "rdfs:label", "full": "..."}, "objects": [{"value": "Person", "lang": "en"}]},
    {"predicate": {"uri": "rdf:type", "full": "..."}, "objects": [{"value": "owl:Class", "uri": "..."}]}
  ],
  "incoming": [
    {"subject": {"uri": "_:node1", "label": "_:node1"}, "predicate": {"uri": "rdf:type", "label": "rdf:type"}}
  ],
  "outgoing": [
    {"predicate": {"uri": "rdfs:subClassOf", "label": "rdfs:subClassOf"}, "object": {"uri": "...", "label": "..."}}
  ]
}
```

- `incoming` and `outgoing` are **paginated** (default limit 50, with `?limit=...&offset=...` params) — prevents huge responses for well-connected nodes
- `properties` groups by predicate for compactness
- Literal values include datatype and language tag when present

**Response** `404 Not Found`:
```json
{"error": "Node not found in graph", "uri": "..."}
```

#### `GET /api/search?q=<search-term>&limit=50&offset=0`
Full-text search across node labels.

Searches `rdfs:label`, `skos:prefLabel`, `skos:altLabel`, and falls back to local name. Returns matching subjects with their best label.

**Response** `200 OK`:
```json
{
  "results": [
    {"uri": "http://...", "label": "Person", "match_property": "rdfs:label", "types": ["owl:Class"]}
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

- `q` is matched case-insensitively as substring
- `total` reflects unfiltered count for pagination UI
- Empty `q` returns nothing (user must type)

### Summary

| Endpoint | Purpose | Used By |
|----------|---------|---------|
| `GET /` | Serves SPA | Browser nav |
| `GET /api/stats` | Graph overview | Initial load |
| `GET /api/sparql?query=` | Arbitrary SPARQL | Advanced users |
| `GET /api/node?uri=` | Node details | Entity panel |
| `GET /api/search?q=` | Text search | Search bar |

### Why Not a Single SPARQL Endpoint?

Dedicated REST endpoints are needed because:
1. **Performance**: `SELECT ?s ?p ?o WHERE { ?s ?p ?o }` is expensive — dedicated endpoints use optimized SPARQL patterns
2. **Usability**: Frontend doesn't need to construct SPARQL for common operations
3. **Pagination**: Node details with pagination require `LIMIT`/`OFFSET` logic that's simpler in dedicated handler code
4. **Error UX**: Structured error responses are easier to handle than raw SPARQL parse errors

## 4. Frontend Architecture

### UI Layout

```
┌─────────────────────────────────────────────────┐
│  [Search bar ██████████████████] [SPARQL ▼]     │  ← Top toolbar
├──────────────────────┬──────────────────────────┤
│                      │                          │
│   Graph View         │   Entity Panel           │
│   (vis-network)      │   (node details)         │
│                      │                          │
│   • Force-directed   │   • Labels               │
│   • Click to select  │   • Types                │
│   • Drag to explore  │   • Properties           │
│   • Zoom / pan       │   • Incoming triples     │
│                      │   • Outgoing triples     │
│                      │                          │
├──────────────────────┴──────────────────────────┤
│  Status bar: "3421 nodes · 15234 triples · Filter: all" │
└─────────────────────────────────────────────────┘
```

### Component Breakdown (all in `app.js`)

1. **Search Controller**
   - Debounced input (300ms) → calls `GET /api/search?q=...`
   - Displays dropdown of matching nodes
   - On select: centers graph on node, highlights it, opens entity panel
   - Keyboard navigation (arrows + Enter)

2. **Graph Renderer**
   - Uses **vis-network** (the maintained community fork of vis.js)
   - Initial load: fetches graph data via a pre-computed query (`SELECT ?s ?p ?o { ... } LIMIT 1000`)
   - Nodes: colored by type (owl:Class, rdfs:Class → blue; individuals → green; literals → not shown as nodes)
   - Edges: labeled with prefix-compressed predicate name, colored by predicate
   - Interaction: click → select → open entity panel; double-click → expand node (fetch its neighborhood)
   - Physics: vis-network's built-in force-directed layout (Barnes-Hut)
   - Performance: if >800 nodes, disable physics animation after stabilization

3. **Entity Panel**
   - Shows when a node is selected
   - Tabs or sections: Labels, Properties, Incoming, Outgoing
   - Incoming/Outgoing are lazily loaded (API pagination)
   - Click on linked node → select that node in graph
   - Close button to deselect

4. **SPARQL Query Panel** (collapsible, for advanced users)
   - Textarea for SPARQL query
   - "Run" button → calls `GET /api/sparql?query=...`
   - Results displayed as table (for SELECT) or message
   - "Load as Graph" button renders results as graph overlay
   - Error display for invalid queries

5. **Filter Bar**
   - Dropdown/checkboxes listing predicates (from `/api/stats`)
   - Toggling a predicate hides/shows edges of that type
   - "Show all" / "Hide all" shortcuts

### Loading States

| State | Behavior |
|-------|----------|
| Initial page load | Fetch `/api/stats`, show "Loading..." spinner. Then fetch initial graph data. |
| Search | Debounced. Show spinner in search dropdown. |
| Node detail | Show "Loading..." in entity panel while fetching. |
| SPARQL query | Run button shows spinner, results appear below. |
| Empty graph | Graph area shows "No triples loaded." |
| Error | Toast/notification in corner. Not a full-page error. |

### Frontend Dependencies (loaded from CDN or bundled)

- `vis-network` (9.x) — graph rendering
- No bundler (vanilla JS served as static files) — keeps build step at zero for MVP

## 5. Data Model Decisions

### Label Resolution Algorithm (`label_utils.py`)

For any resource URI, resolve a human-readable label:

```
1. Look for literal triples with predicate rdfs:label
   a. Prefer literal with language tag "en" or "en-*"
   b. Fall back to literal with no language tag
   c. Fall back to any language tag alphabetically
2. If no rdfs:label, look for skos:prefLabel (same language preference)
3. If neither, look for skos:altLabel (same language preference)
4. If none of the above, look for foaf:name, dcterms:title, dc:title
5. Final fallback: URI → prefix-compressed local name
   (e.g., http://xmlns.com/foaf/0.1/Person → "foaf:Person")
   For blank nodes, use "_:id-abbrev" (e.g., "_:n1")
```

This logic lives in `label_utils.py` as a `resolve_label(graph, uri)` function and is reused by `server.py` and `sparql_engine.py`.

### URI Prefix Compression (`label_utils.py`)

**Approach**: Maintain a `PrefixMap` (dict of prefix → namespace URI).

Sources:
1. **Built-in well-known prefixes** (always available):
   ```
   rdf:  http://www.w3.org/1999/02/22-rdf-syntax-ns#
   rdfs: http://www.w3.org/2000/01/rdf-schema#
   owl:  http://www.w3.org/2002/07/owl#
   xsd:  http://www.w3.org/2001/XMLSchema#
   skos: http://www.w3.org/2004/02/skos/core#
   foaf: http://xmlns.com/foaf/0.1/
   dc:   http://purl.org/dc/elements/1.1/
   dct:  http://purl.org/dc/terms/
   ```
2. **From the graph** — `rdflib.Graph.namespace_manager` provides all prefixes declared in the Turtle file
3. **CLI override** — `--prefix-map` flag accepts a JSON file of `{"prefix": "namespace"}`

Compression: `compress(uri)` returns the shortest matching `prefix:localname` or the full URI if no prefix matches.

Decompression: `expand(prefixed)` returns the full URI for known prefixes (used internally, not exposed in MVP).

### Blank Nodes

Blank nodes are common in RDF but hard to visualize meaningfully.

- **Display**: `_:nodehash` truncated to `_:abc123...`
- **Graph inclusion**: Include blank nodes if they connect to named resources; otherwise exclude isolated blank node clusters
- **Filtering**: Provide a toggle "Show blank nodes" (default: on for connected, off for isolated)
- **SPARQL**: Blank nodes are queryable via `?s` binding; the API preserves their internal IDs

### Large Graph Handling

| Strategy | Implementation |
|----------|---------------|
| Initial load limit | First fetch: 1000 most-connected nodes (by degree) via SPARQL |
| Incremental expansion | Double-click a node → fetch its 1-hop neighborhood via SPARQL DESCRIBE or CONSTRUCT |
| Pagination | `/api/node?uri=` uses `LIMIT/OFFSET` for incoming/outgoing lists |
| Search-driven navigation | Users search for specific nodes rather than browsing the full graph |

## 6. Performance Considerations

### Accepted Constraints (MVP)

| Aspect | Expectation |
|--------|-------------|
| Turtle file size | Up to ~50 MB (tens of thousands of triples) |
| rdflib memory | ~5–10x file size (in-memory Graph) — 50 MB file → ~250–500 MB RAM |
| Initial load time | <5 seconds for files up to 50 MB |
| SPARQL query time | <1 second for most queries; complex ones up to 30s with timeout |
| vis-network render | Smooth up to ~1000 nodes; acceptable at 2000; degrade beyond |
| Concurrent users | 1 (local-only) with occasional 2nd (LAN) |

### Mitigations

1. **SPARQL query timeout**: `sparql_engine.py` wraps queries with a timeout context manager (30s default). Long-running queries return 408.
2. **Graph is loaded once**: No repeated file I/O after startup.
3. **Frontend throttling**: vis-network physics is disabled after stabilization. Search is debounced.
4. **Lazy node details**: Entity panel data is fetched on demand, not preloaded.
5. **No WebSockets**: Simple HTTP request-response keeps complexity low.

### When to Worry

- Files >100 MB with >500K triples: rdflib becomes slow for SPARQL. This is an MVP limitation; streaming/federated queries are out of scope.
- Graphs with >5000 nodes: vis-network will lag. Consider server-side filtering (by type, by connected component) to reduce what's rendered.

## 7. Edge Cases

### Empty Graph
- **CLI**: If `--ttl` points to an empty file or a file with no triples, print a warning and start the server. The UI will show "No triples loaded."
- **API**: `/api/stats` returns all zeros. `/api/search` returns empty. `/api/sparql` returns empty results.
- **Frontend**: Graph area shows a centered message "Graph is empty — load a Turtle file with triples."

### No Labels on Nodes
- If a node has no `rdfs:label`, `skos:prefLabel`, etc., fall back to prefix-compressed URI (e.g., `foaf:Person`).
- If even prefix compression fails (unknown namespace), display the full URI.
- If the URI is very long (>80 chars), truncate with ellipsis: `http://example.com/very/long/uri/...`.

### Invalid Turtle File
- **CLI**: `graph_loader.py` catches `rdflib.exceptions.ParserError` and prints a clear error message with file path and line number (rdflib provides these). Exit with code 1.
- **CLI stub**: if `--ttl` path doesn't exist, print "File not found: /path/to/file.ttl" and exit.

### Lots of Blank Nodes
- **Performance**: Blank nodes with `_:genid` patterns can create millions of unique IDs. Use a SPARQL pattern that filters isolated blank nodes: `FILTER NOT EXISTS { ?s ?p ?o FILTER(isBlank(?s)) }` for the default view.
- **Display**: Blank nodes are shown with a different visual style (dashed border, grey fill) to distinguish from named resources.
- **Toggle**: Add a "Show blank nodes" checkbox in the filter bar.

### Circular References
- RDF allows cycles (e.g., `A → knows → B → knows → A`). vis-network's physics handles this naturally (nodes repel each other).
- No special handling needed for rendering. For entity panel incoming/outgoing, we deduplicate and avoid infinite recursion by capping the depth at 1 hop.

### SPARQL Injection / Malformed Queries
- **Validation**: Reject non-SELECT queries (no INSERT, DELETE, UPDATE, DROP, CLEAR, CREATE, LOAD) in MVP. This prevents accidental or malicious graph modification.
- **Error handling**: Malformed SPARQL returns 400 with rdflib's parse error message.
- **Since MVP is localhost-only**, the attack surface is minimal, but the guardrails are good practice.

### Unicode / Non-ASCII Labels
- Turtle supports full Unicode. The API returns JSON (UTF-8); the frontend renders it as-is.
- vis-network handles Unicode correctly.
- Search (`/api/search`) should be case-insensitive for ASCII but respect the dataset's encoding for other scripts (rdflib handles this).

### Language-Tagged Literals
- `rdfs:label` often has language tags.
- Label resolution prefers `@en` > no tag > alphabetical first tag.
- The entity panel shows all language variants in a collapsible section.
- The frontend displays the best label with a small language badge (e.g., "Person [en]") if multiple variants exist.

## 8. Out of Scope for MVP

### Explicitly Not Building

| Feature | Rationale |
|---------|-----------|
| **File watching / auto-reload** | The user already decided this. Add `--watch` in a follow-up. |
| **Multiple concurrent users** | Local-first tool. Session isolation adds auth/state complexity. |
| **Authentication / authorization** | Binds to localhost by default. LAN users are trusted. |
| **SPARQL Update (write)** | Read-only visualization tool. Write support introduces validation and conflict issues. |
| **Export / share** | Save as PNG, PDF, or share graph URL — all post-MVP. Users can screenshot. |
| **Saved queries** | No database, no persistence layer beyond the Turtle file. |
| **Plugin system** | Would need a defined extension API. Not for MVP. |
| **Docker image** | Overkill for `pip install` distribution. |
| **Config file (YAML/TOML)** | CLI flags suffice for MVP. Config file adds a discovery problem. |
| **Turtle file download / upload via UI** | User provides file path via CLI; no browser file upload. |
| **Streaming parser** | rdflib loads entirely into memory. Streaming would require `rdflib` changes or a different library. |
| **Federated SPARQL** | The graph is local only; no remote SPARQL endpoint support. |
| **Incremental loading (multiple files at different times)** | Load all files at startup. Reload requires restart. |
| **SHACL / RDFS reasoning** | No inferencing. The graph is displayed as-is. |
| **Mobile-responsive layout** | Desktop-first. A minimum width of 900px is assumed. |

### Future Considerations (noted but not blocking)

- `--watch` flag for auto-reload
- Named graph support (`GRAPH ?g { ... }`)
- TTL output / export of filtered subgraph
- Configurable color scheme / legend
- OWL ontology class hierarchy rendering (tree + graph hybrid)

## 9. Recommended Issue Labels

| Label | Reason |
|-------|--------|
| `architecture` | Core design document |
| `design-doc` | Formal design specification |
| `mvp` | Defines the initial deliverable scope |
| `good-first-issue` | The architecture doc is the starting point for all contributors |
| `documentation` | It documents the system design |

**Proposed**: apply `architecture`, `design-doc`, `mvp` to this issue.

---

## Implementation Sequence (Suggested Order)

This is the order in which the modules should be built, each building on the previous:

| Step | Files | What to Build |
|------|-------|---------------|
| 1 | `pyproject.toml`, `__init__.py`, `__main__.py` | Package skeleton — `pip install -e .` works |
| 2 | `graph_loader.py` | Load Turtle file, validate, expose Graph + namespace bindings |
| 3 | `label_utils.py` | Label resolution + prefix compression — test with known Turtle |
| 4 | `sparql_engine.py` | SPARQL execution, result formatting, timeout |
| 5 | `server.py` | Flask app, all REST endpoints, static file serving |
| 6 | `tests/` | Test suite for all modules |
| 7 | `static/index.html`, `static/app.js`, `static/style.css` | Frontend SPA |
| 8 | `cli.py` | CLI entry point, argument parsing, wiring |
| 9 | `README.md` | Documentation |

Steps 7 and 8 can be parallelized (frontend and CLI are independent).
