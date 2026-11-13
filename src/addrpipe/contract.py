"""The schema contract an input file must satisfy before it is allowed into the lake."""

from __future__ import annotations

import re

import geopandas as gpd

# Column name -> expected kind. "text" columns may be null, but every non-null value must be a string.
COLUMNS: dict[str, str] = {
    "source": "text",
    "source_id": "int",
    "house_number": "text",
    "number_suffix": "text",
    "unit": "text",
    "street_name": "text",
    "street_type": "text",
    "street_dir": "text",
    "full_address": "text",
    "city": "text",
    "province": "text",
    "parsed": "bool",
    "raw_street_type": "text",
}

# Columns that must never be null.
REQUIRED: tuple[str, ...] = ("source", "source_id", "parsed", "province")

PROVINCE_PATTERN = re.compile(r"^[A-Z]{2}$")
SOURCE_PATTERN = re.compile(r"^[a-z0-9_]{1,64}$")
EXPECTED_CRS = "EPSG:4326"


class ContractError(ValueError):
    """Raised when an input file breaks the contract. The message lists every violation."""

    def __init__(self, violations: list[str]):
        self.violations = violations
        super().__init__("; ".join(violations))


def _is_text(value) -> bool:
    return isinstance(value, str)


def _is_int(value) -> bool:
    # bool is a subclass of int, and a bool in an id column is a bug, not a number.
    if hasattr(value, "dtype"):
        return value.dtype.kind in "iu"
    return isinstance(value, int) and not isinstance(value, bool)


def _is_bool(value) -> bool:
    if hasattr(value, "dtype"):
        return value.dtype.kind == "b"
    return isinstance(value, bool)


_KIND_CHECKS = {"text": _is_text, "int": _is_int, "bool": _is_bool}


def validate(gdf: gpd.GeoDataFrame) -> None:
    """Raise ContractError listing every violation, or return None if the frame is acceptable."""
    problems: list[str] = []

    if len(gdf) == 0:
        problems.append("file has no rows")

    missing = [c for c in COLUMNS if c not in gdf.columns]
    extra = [c for c in gdf.columns if c not in COLUMNS and c != gdf.geometry.name]
    if missing:
        problems.append(f"missing columns: {', '.join(missing)}")
    if extra:
        problems.append(f"unexpected columns: {', '.join(extra)}")

    if gdf.crs is None or gdf.crs.to_string() != EXPECTED_CRS:
        problems.append(f"crs is {gdf.crs.to_string() if gdf.crs else None}, expected {EXPECTED_CRS}")

    kinds = set(gdf.geometry.geom_type.dropna().unique())
    if kinds - {"Point"}:
        problems.append(f"geometry must be Point, found {', '.join(sorted(kinds - {'Point'}))}")
    if gdf.geometry.isna().any() or gdf.geometry.is_empty.any():
        problems.append("some rows have null or empty geometry")

    for column, kind in COLUMNS.items():
        if column not in gdf.columns:
            continue
        values = gdf[column].dropna()
        check = _KIND_CHECKS[kind]
        bad = [v for v in values.head(1000) if not check(v)]
        if bad:
            problems.append(f"column {column}: expected {kind}, found {type(bad[0]).__name__} ({bad[0]!r})")
        if column in REQUIRED and gdf[column].isna().any():
            problems.append(f"column {column}: {int(gdf[column].isna().sum())} null values")

    if "province" in gdf.columns and not any("column province" in p for p in problems):
        wrong = gdf["province"].dropna()
        wrong = wrong[~wrong.map(lambda v: bool(PROVINCE_PATTERN.match(v)))]
        if len(wrong):
            example = wrong.iloc[0]
            problems.append(f"column province: {len(wrong)} values are not a two-letter code (for example {example!r})")

    if "source" in gdf.columns:
        sources = gdf["source"].dropna().unique()
        if len(sources) != 1:
            problems.append(f"file must hold exactly one source, found {len(sources)}")
        elif not isinstance(sources[0], str) or not SOURCE_PATTERN.match(sources[0]):
            # The source name becomes a directory name in the lake, so it is restricted.
            problems.append(f"source {sources[0]!r} must be lowercase letters, digits and underscores")

    if problems:
        raise ContractError(problems)
