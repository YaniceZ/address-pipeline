"""Load one standardized GeoPackage into the GeoParquet lake."""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

import duckdb
import geopandas as gpd

from addrpipe.contract import COLUMNS, ContractError, validate
from addrpipe.warehouse import Layout, utcnow


@dataclass(frozen=True)
class IngestResult:
    file: str
    source: str | None
    status: str  # loaded | unchanged | rejected
    rows: int
    message: str = ""


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record(con, run_id, started, path, source, sha, rows, status, message) -> None:
    con.execute(
        "INSERT INTO run_log VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [run_id, source, path.name, sha, rows, status, message, started, utcnow()],
    )


def _last_loaded_hash(con: duckdb.DuckDBPyConnection, source: str) -> str | None:
    row = con.execute(
        "SELECT input_sha256 FROM run_log WHERE source = ? AND status = 'loaded' ORDER BY finished_at DESC LIMIT 1",
        [source],
    ).fetchone()
    return row[0] if row else None


def _to_lake_frame(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    out = gdf.copy()
    # Force text columns to a real string type so an all-null column does not become Arrow's "null" type,
    # which breaks when files with different content are read together.
    for column, kind in COLUMNS.items():
        if kind == "text":
            out[column] = out[column].astype("string")
    out["lon"] = out.geometry.x
    out["lat"] = out.geometry.y
    return out


def ingest(con: duckdb.DuckDBPyConnection, layout: Layout, path: Path) -> IngestResult:
    """Validate and load one file. A file that breaks the contract is rejected and the lake is left as it was."""
    path = Path(path)
    run_id = uuid.uuid4().hex[:12]
    started = utcnow()
    sha = sha256_of(path)

    try:
        gdf = gpd.read_file(path)
        validate(gdf)
    except ContractError as error:
        source = None
        if "source" in gdf.columns and gdf["source"].nunique() == 1:
            source = str(gdf["source"].iloc[0])
        _record(con, run_id, started, path, source, sha, len(gdf), "rejected", str(error))
        return IngestResult(path.name, source, "rejected", len(gdf), str(error))
    except Exception as error:  # unreadable file, driver error and so on
        message = f"could not read file: {error}"
        _record(con, run_id, started, path, None, sha, 0, "rejected", message)
        return IngestResult(path.name, None, "rejected", 0, message)

    source = str(gdf["source"].iloc[0])
    target = layout.partition(source) / "part.parquet"

    if _last_loaded_hash(con, source) == sha and target.exists():
        _record(con, run_id, started, path, source, sha, len(gdf), "unchanged", "input identical to last load")
        return IngestResult(path.name, source, "unchanged", len(gdf), "input identical to last load")

    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".parquet.tmp")
    _to_lake_frame(gdf).to_parquet(temp, index=False)
    os.replace(temp, target)  # the partition is swapped in one step, so readers never see half a file

    _record(con, run_id, started, path, source, sha, len(gdf), "loaded", "")
    return IngestResult(path.name, source, "loaded", len(gdf))
