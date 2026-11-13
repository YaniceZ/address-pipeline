"""The DuckDB warehouse: layout on disk, run history, SQL models and SQL data checks."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

import duckdb


@dataclass(frozen=True)
class Layout:
    """Where everything lives under one root directory."""

    root: Path

    @property
    def lake(self) -> Path:
        return self.root / "lake" / "addresses"

    @property
    def db(self) -> Path:
        return self.root / "warehouse.duckdb"

    def partition(self, source: str) -> Path:
        return self.lake / f"source={source}"

    def lake_glob(self) -> str:
        # DuckDB accepts forward slashes on every platform.
        return (self.lake / "*" / "*.parquet").as_posix()


RUN_LOG_DDL = """
CREATE TABLE IF NOT EXISTS run_log (
    run_id        VARCHAR,
    source        VARCHAR,
    input_file    VARCHAR,
    input_sha256  VARCHAR,
    rows          BIGINT,
    status        VARCHAR,   -- loaded | unchanged | rejected
    message       VARCHAR,
    started_at    TIMESTAMP,
    finished_at   TIMESTAMP
)
"""

CHECK_RESULTS_DDL = """
CREATE TABLE IF NOT EXISTS check_results (
    run_at       TIMESTAMP,
    check_name   VARCHAR,
    severity     VARCHAR,
    description  VARCHAR,
    failed_rows  BIGINT,
    passed       BOOLEAN,
    sample       VARCHAR
)
"""


def connect(layout: Layout) -> duckdb.DuckDBPyConnection:
    layout.root.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(layout.db))
    con.execute(RUN_LOG_DDL)
    con.execute(CHECK_RESULTS_DDL)
    return con


def utcnow() -> datetime:
    # DuckDB TIMESTAMP is naive, so store UTC without tzinfo.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _sql_files(package_dir: str) -> list[tuple[str, str]]:
    folder = resources.files("addrpipe").joinpath(package_dir)
    files = sorted((p for p in folder.iterdir() if p.name.endswith(".sql")), key=lambda p: p.name)
    return [(p.name.removesuffix(".sql"), p.read_text(encoding="utf-8")) for p in files]


def build(con: duckdb.DuckDBPyConnection, layout: Layout) -> list[str]:
    """Rebuild every model from the lake. Returns the model names in the order they ran."""
    if not any(layout.lake.glob("*/*.parquet")):
        raise FileNotFoundError(f"no parquet files under {layout.lake}; run ingest first")
    ran = []
    for name, sql in _sql_files("models"):
        con.execute(sql.replace("{lake_glob}", layout.lake_glob()))
        ran.append(name)
    return ran


@dataclass(frozen=True)
class CheckResult:
    name: str
    severity: str
    description: str
    failed_rows: int
    sample: list

    @property
    def passed(self) -> bool:
        return self.failed_rows == 0


_HEADER = re.compile(r"^--\s*(\w+):\s*(.+?)\s*$")


def _parse_header(sql: str) -> dict[str, str]:
    meta = {}
    for line in sql.splitlines():
        match = _HEADER.match(line)
        if not match:
            break
        meta[match.group(1)] = match.group(2)
    return meta


def run_checks(con: duckdb.DuckDBPyConnection) -> list[CheckResult]:
    """Run every SQL check. A check is a query that returns the offending rows; no rows means it passed."""
    run_at = utcnow()
    results = []
    for name, sql in _sql_files("checks"):
        meta = _parse_header(sql)
        cursor = con.execute(sql)
        columns = [d[0] for d in cursor.description]
        rows = cursor.fetchall()
        sample = [dict(zip(columns, row, strict=True)) for row in rows[:5]]
        result = CheckResult(
            name=name,
            severity=meta.get("severity", "error"),
            description=meta.get("description", ""),
            failed_rows=len(rows),
            sample=sample,
        )
        con.execute(
            "INSERT INTO check_results VALUES (?, ?, ?, ?, ?, ?, ?)",
            [run_at, name, result.severity, result.description, result.failed_rows, result.passed,
             json.dumps(sample, default=str)],
        )
        results.append(result)
    return results
