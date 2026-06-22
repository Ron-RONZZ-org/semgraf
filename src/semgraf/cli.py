"""Command-line interface for semgraf."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from semgraf import __version__
from semgraf.graph_loader import GraphLoadError, load_ttl_files
from semgraf.label_utils import PrefixMap
from semgraf.server import create_app


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="semgraf",
        description="Local-first semantic graph visualizer",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"semgraf {__version__}",
    )
    parser.add_argument(
        "--ttl",
        required=True,
        nargs="+",
        type=Path,
        help="Turtle (.ttl) file(s) to load",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to listen on (default: 8080)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable Flask debug mode",
    )
    parser.add_argument(
        "--prefix-map",
        type=Path,
        default=None,
        help="Path to JSON file with custom prefix mappings: {\"prefix\": \"namespace\"}",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """CLI entry point: load Turtle files and start the web server."""
    args = _parse_args(argv)

    # --- Load Turtle files ---
    missing = [p for p in args.ttl if not p.exists()]
    if missing:
        print(f"Error: file(s) not found — {', '.join(str(p) for p in missing)}", file=sys.stderr)
        sys.exit(1)

    non_ttl = [p for p in args.ttl if p.suffix.lower() not in (".ttl", ".turtle")]
    if non_ttl:
        print(
            f"Warning: expected .ttl files, got: {', '.join(str(p) for p in non_ttl)}",
            file=sys.stderr,
        )

    try:
        graph = load_ttl_files(args.ttl)
    except (GraphLoadError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Loaded {len(graph)} triples from {len(args.ttl)} file(s).", file=sys.stderr)

    # --- Prefix map ---
    overrides: dict[str, str] | None = None
    if args.prefix_map is not None:
        try:
            with open(args.prefix_map) as f:
                overrides = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Error loading prefix map: {exc}", file=sys.stderr)
            sys.exit(1)

    prefix_map = PrefixMap(graph, overrides=overrides)
    app = create_app(graph, prefix_map=prefix_map)

    # --- Start server ---
    print(
        f"semgraf running at http://{args.host}:{args.port}",
        file=sys.stderr,
    )
    app.run(host=args.host, port=args.port, debug=args.debug)
