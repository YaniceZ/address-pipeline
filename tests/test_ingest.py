import geopandas as gpd

from addrpipe.ingest import ingest

from .conftest import make_frame


def run_log(con):
    return con.execute("SELECT source, status, rows FROM run_log ORDER BY finished_at").fetchall()


def test_load_writes_geoparquet_with_lon_lat(con, layout, write_gpkg):
    result = ingest(con, layout, write_gpkg("alpha", n=5))

    assert (result.status, result.source, result.rows) == ("loaded", "alpha", 5)
    stored = gpd.read_parquet(layout.partition("alpha") / "part.parquet")
    assert len(stored) == 5
    assert {"lon", "lat"} <= set(stored.columns)
    assert stored["lon"].iloc[0] == stored.geometry.x.iloc[0]
    assert run_log(con) == [("alpha", "loaded", 5)]


def test_identical_file_is_skipped(con, layout, write_gpkg):
    path = write_gpkg("alpha", n=5)
    ingest(con, layout, path)
    stamp = (layout.partition("alpha") / "part.parquet").stat().st_mtime_ns

    again = ingest(con, layout, path)

    assert again.status == "unchanged"
    assert (layout.partition("alpha") / "part.parquet").stat().st_mtime_ns == stamp
    assert [status for _, status, _ in run_log(con)] == ["loaded", "unchanged"]


def test_changed_file_replaces_the_partition(con, layout, write_gpkg):
    ingest(con, layout, write_gpkg("v1", n=5))
    result = ingest(con, layout, write_gpkg("v2", n=8))

    assert result.status == "loaded"
    assert len(gpd.read_parquet(layout.partition("alpha") / "part.parquet")) == 8  # replaced, not appended


def test_deleted_lake_is_reloaded_even_if_the_file_is_unchanged(con, layout, write_gpkg):
    path = write_gpkg("alpha", n=5)
    ingest(con, layout, path)
    (layout.partition("alpha") / "part.parquet").unlink()

    assert ingest(con, layout, path).status == "loaded"


def test_rejected_file_leaves_the_lake_untouched(con, layout, write_gpkg):
    ingest(con, layout, write_gpkg("good", n=5))
    before = (layout.partition("alpha") / "part.parquet").read_bytes()

    result = ingest(con, layout, write_gpkg("bad", frame=make_frame(n=9, province=True)))

    assert result.status == "rejected"
    assert "province" in result.message
    assert (layout.partition("alpha") / "part.parquet").read_bytes() == before
    assert [status for _, status, _ in run_log(con)] == ["loaded", "rejected"]


def test_unreadable_file_is_rejected_not_raised(con, layout, tmp_path):
    broken = tmp_path / "broken.gpkg"
    broken.write_bytes(b"not a geopackage")

    result = ingest(con, layout, broken)

    assert result.status == "rejected"
    assert "could not read" in result.message
    assert not layout.lake.exists()


def test_two_sources_get_separate_partitions(con, layout, write_gpkg):
    ingest(con, layout, write_gpkg("a", source="alpha", n=3))
    ingest(con, layout, write_gpkg("b", source="beta", n=4, province="ON"))

    assert (layout.partition("alpha") / "part.parquet").exists()
    assert (layout.partition("beta") / "part.parquet").exists()
