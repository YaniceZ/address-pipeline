"""Command line entry point: addrpipe ingest | build | check | run | status."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from addrpipe import warehouse
from addrpipe.ingest import IngestResult, ingest
from addrpipe.warehouse import Layout

EXIT_CHECK_FAILED = 1
EXIT_REJECTED = 2


def _ingest_files(con, layout: Layout, files: list[Path]) -> list[IngestResult]:
    results = []
    for path in files:
        result = ingest(con, layout, path)
        results.append(result)
        label = result.source or "?"
        print(f"  {result.status:<9} {label:<16} {result.rows:>8,} rows  {result.file}")
        if result.status == "rejected":
            for violation in result.message.split("; "):
                print(f"            - {violation}")
    return results


def _build(con, layout: Layout) -> bool:
    try:
        models = warehouse.build(con, layout)
    except FileNotFoundError as error:
        print(f"  {error}")
        return False
    print(f"  built {len(models)} models: {', '.join(models)}")
    return True


def _check(con) -> int:
    results = warehouse.run_checks(con)
    errors = 0
    for r in results:
        mark = "pass" if r.passed else ("FAIL" if r.severity == "error" else "warn")
        print(f"  {mark:<5} {r.name}" + ("" if r.passed else f"  ({r.failed_rows} rows)"))
        if not r.passed:
            print(f"        {r.description}")
            for row in r.sample[:3]:
                print(f"        e.g. {row}")
            errors += r.severity == "error"
    return errors


def _status(con) -> None:
    print("Recent loads")
    rows = con.execute(
        "SELECT finished_at, source, status, rows, input_file FROM run_log ORDER BY finished_at DESC LIMIT 10"
    ).fetchall()
    for finished, source, status, n, file in rows:
        print(f"  {finished:%Y-%m-%d %H:%M:%S}  {status:<9} {source or '?':<16} {n:>8,}  {file}")
    if not rows:
        print("  none yet")
    tables = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
    if "source_summary" in tables:
        print("\nSources in the warehouse")
        rows = con.execute(
            "SELECT source, province, addresses, parsed_pct, west, south, east, north FROM source_summary ORDER BY source"
        ).fetchall()
        for source, province, n, parsed, west, south, east, north in rows:
            box = f"[{west:.3f}, {south:.3f}, {east:.3f}, {north:.3f}]"
            print(f"  {source:<16} {province}  {n:>8,} addresses  {parsed}% parsed  bbox {box}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="addrpipe", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("pipeline_out"), help="where the lake and warehouse live")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (("ingest", "validate files and load them into the lake"), ("run", "ingest, build and check")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("files", nargs="+", type=Path, help="standardized GeoPackage files")
    sub.add_parser("build", help="rebuild the SQL models from the lake")
    sub.add_parser("check", help="run the SQL data checks")
    sub.add_parser("status", help="show recent loads and what is in the warehouse")

    args = parser.parse_args(argv)
    layout = Layout(args.root)
    con = warehouse.connect(layout)
    try:
        if args.command == "ingest":
            results = _ingest_files(con, layout, args.files)
            return EXIT_REJECTED if any(r.status == "rejected" for r in results) else 0
        if args.command == "build":
            return 0 if _build(con, layout) else EXIT_REJECTED
        if args.command == "check":
            return EXIT_CHECK_FAILED if _check(con) else 0
        if args.command == "status":
            _status(con)
            return 0

        print("ingest")
        results = _ingest_files(con, layout, args.files)
        rejected = any(r.status == "rejected" for r in results)
        print("build")
        if not _build(con, layout):
            return EXIT_REJECTED
        print("check")
        failed = _check(con)
        if rejected:
            print("\nsome files were rejected and not loaded; the warehouse holds the previous data for those sources")
            return EXIT_REJECTED
        return EXIT_CHECK_FAILED if failed else 0
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
