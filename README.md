# semgraf — semantic graph visualizer

Local-first semantic graph visualizer. Load Turtle (`.ttl`) RDF files
and browse them interactively via a web UI with SPARQL querying.

```
semgraf --ttl my-knowledge-base.ttl
# → http://127.0.0.1:8080
```

## Features

- **SPARQL-powered** — full SPARQL 1.1 SELECT support via rdflib
- **Interactive graph** — vis-network force-directed layout, click to inspect, double-click to expand
- **Node inspector** — labels, types, incoming/outgoing triples with pagination
- **Search** — debounced full-text search across `rdfs:label`, `skos:prefLabel`, etc.
- **SPARQL panel** — run ad-hoc queries and load results as graph overlay
- **Local-first** — runs on localhost. Zero external network dependencies. Your data stays yours.
- **One-shot** — load Turtle file(s) at startup, no file-watching (MVP)

## Install

```bash
pip install semgraf
```

Or from source:

```bash
git clone https://github.com/Ron-RONZZ-org/semgraf
cd semgraf
pip install -e .
```

## Usage

```bash
# Load one or more Turtle files
semgraf --ttl data.ttl

# Custom host/port
semgraf --ttl data.ttl --host 0.0.0.0 --port 9090

# Custom prefix mappings
semgraf --ttl data.ttl --prefix-map my-prefixes.json

# Enable Flask debug mode
semgraf --ttl data.ttl --debug
```

Then open [http://127.0.0.1:8080](http://127.0.0.1:8080) in your browser.

### Prefix map file format

```json
{
  "ex": "http://example.org/",
  "my": "http://my-namespace.com/ontology#"
}
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Web UI |
| `GET /api/stats` | Graph statistics (counts, predicates, namespaces) |
| `GET /api/sparql?query=...` | SPARQL 1.1 SELECT proxy |
| `GET /api/node?uri=...` | Node details (types, labels, in/out triples) |
| `GET /api/search?q=...` | Full-text search across labels |

## Label Resolution

Resources are displayed with human-readable labels following this priority chain:

1. `rdfs:label` (`@en` → no tag → alphabetically first)
2. `skos:prefLabel`
3. `skos:altLabel`
4. `foaf:name`, `dcterms:title`, `dc:title`
5. Prefix-compressed URI (e.g., `foaf:Person`)
6. Full URI (last resort)

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## License

AGPL-3.0 — see [LICENSE](LICENSE).
