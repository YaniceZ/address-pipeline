# address-pipeline

![tests](https://github.com/YaniceZ/address-pipeline/actions/workflows/ci.yml/badge.svg)

Loads standardized civic address GeoPackages (the output of [civic-address-qa](https://github.com/YaniceZ/civic-address-qa)) into a GeoParquet lake and a DuckDB warehouse. Each file has to pass a schema contract before it is allowed in, the warehouse tables are built with plain SQL, and a set of SQL checks runs over the result.

```
GeoPackage ──> contract ──> GeoParquet lake ──> DuckDB models ──> SQL checks
                  │         (one partition        addresses         exit code 1
               rejected      per source)          street_summary    if an error
               and logged                         grid_density      check fails
                                                  source_summary
```

```
addrpipe run thunder_bay.gpkg west_kelowna.gpkg
```

```
ingest
  loaded    thunder_bay        45,102 rows  thunder_bay.gpkg
  unchanged west_kelowna       18,255 rows  west_kelowna.gpkg
build
  built 4 models: 01_addresses, 02_street_summary, 03_grid_density, 04_source_summary
check
  pass  01_unique_source_id
  pass  02_core_fields_present
  pass  03_inside_canada
  pass  04_parse_rate
  pass  05_one_province_per_source
  warn  06_repeated_addresses  (2 rows)
        the same address text appears more than once in a source without a unit number
        e.g. {'source': 'thunder_bay', 'city': 'FWFN', 'full_address': '950 CHIPPEWA RD', 'copies': 2}
  pass  07_row_count_drop
```

## A bug the contract caught

The first time I ran this on the real output of civic-address-qa, it rejected Thunder Bay:

```
  rejected  thunder_bay        45,102 rows  thunder_bay.gpkg
            - column province: expected text, found bool (True)
```

`sources.yaml` had `province: ON` unquoted. YAML 1.1 reads `ON` as the boolean `True`, so every Thunder Bay row had `True` in the province column. civic-address-qa's own tests passed because they build the config as a Python dict. I fixed the YAML there and added a test that loads the real `sources.yaml`. The rejected load is still in the `run_log` table, and the second run loaded the corrected file.

## How it works

**Contract** (`contract.py`). Before anything is written, the file must have exactly the expected columns, text columns that hold strings, an integer id, a boolean `parsed`, EPSG:4326 point geometry, a two-letter province, and one source name made of lowercase letters, digits and underscores (it becomes a directory name). All violations are reported together. A rejected file is logged and the lake is not touched.

**Lake** (`ingest.py`). One GeoParquet file per source at `lake/addresses/source=<name>/part.parquet`, with `lon` and `lat` columns added. A new file is written beside the old one and swapped in with `os.replace`, so a reader never sees a half-written partition. The input's SHA-256 goes into `run_log`; if the same file is loaded again it is skipped.

**Models** (`models/*.sql`). Numbered SQL files, each one `CREATE OR REPLACE TABLE`, run in order and rebuilt in full every time:

| Table | Contents |
| --- | --- |
| `addresses` | every source in one table, plus an integer house number |
| `street_summary` | addresses per street, lowest and highest number (1,661 streets across the two sources) |
| `grid_density` | address counts on a 0.01 degree grid (410 cells for Thunder Bay, 105 for West Kelowna) |
| `source_summary` | per source: rows, parse rate, bounding box, last load time |

**Checks** (`checks/*.sql`). A check is a query that returns the offending rows; no rows means it passed. A header comment sets the description and whether a failure is an `error` (exit code 1) or a `warn`. Results are stored in `check_results`.

| Check | Severity |
| --- | --- |
| `source_id` unique within a source | error |
| parsed rows have a house number and street name | error |
| every point inside a bounding box around Canada | error |
| at most 1% of a source unparsed | error |
| one province per source | error |
| same address text repeated without a unit | warn |
| a reload shrank a source by more than 10% against the previous load | warn |

**Exit codes.** `0` all good, `1` an error-level check failed, `2` a file was rejected or there was nothing to build.

## Usage

```
python -m venv .venv
.venv\Scripts\activate            # source .venv/bin/activate on macOS/Linux
pip install -e ".[dev]"

addrpipe run path/to/thunder_bay.gpkg path/to/west_kelowna.gpkg
addrpipe status                   # recent loads and what is in the warehouse
addrpipe ingest file.gpkg         # or the steps on their own: ingest, build, check
pytest
```

Output goes to `pipeline_out/` (change it with `--root`): `warehouse.duckdb` and `lake/`. Query it with any DuckDB client:

```sql
SELECT street_name, street_type, addresses FROM street_summary ORDER BY addresses DESC LIMIT 5;
```

## Numbers

On a laptop, both sources (63,357 addresses) go from GeoPackage to checked warehouse in about 2 seconds. The Thunder Bay lake file is 2.5 MB against 7.4 MB for the GeoPackage it came from. A repeat run takes about the same time, because the models are rebuilt every run; the hash check only saves the parquet write.

## Layout

```
src/addrpipe/
  contract.py      the schema contract
  ingest.py        validate, write the partition, log the run
  warehouse.py     layout on disk, run_log, running models and checks
  cli.py           addrpipe command
  models/          SQL tables, run in filename order
  checks/          SQL checks
tests/             37 tests on small synthetic files; no network or real data needed
```

## Limitations

- It runs on one machine and has no scheduler. To run it daily you would put `addrpipe run` in cron or Windows Task Scheduler.
- Models are rebuilt in full on every run. That is fine at 63,000 rows and would need incremental models at tens of millions.
- A file is read into memory in one piece.
- Geometry is stored as GeoParquet, but the SQL works from `lon` and `lat`. It does not use DuckDB's spatial extension, so there are no spatial joins yet, and the grid is in degrees rather than metres.
- The check thresholds (1% unparsed, 10% shrink) are written into the SQL files, not configured.
- Tested on Windows locally and on Linux in CI. Only two sources so far.

## License

MIT
