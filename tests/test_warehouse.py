import pytest

from addrpipe import warehouse
from addrpipe.ingest import ingest

from .conftest import make_frame


def load(con, layout, write_gpkg, name, **kwargs):
    result = ingest(con, layout, write_gpkg(name, **kwargs))
    assert result.status == "loaded", result.message
    return result


def by_name(results):
    return {r.name.split("_", 1)[1]: r for r in results}


def test_build_needs_data(con, layout):
    with pytest.raises(FileNotFoundError):
        warehouse.build(con, layout)


def test_models_are_built_from_the_lake(con, layout, write_gpkg):
    load(con, layout, write_gpkg, "a", source="alpha", n=6)
    load(con, layout, write_gpkg, "b", source="beta", n=4, province="ON", lon0=-80.0, lat0=44.0)

    models = warehouse.build(con, layout)

    assert models == ["01_addresses", "02_street_summary", "03_grid_density", "04_source_summary"]
    assert con.execute("SELECT count(*) FROM addresses").fetchone()[0] == 10
    assert con.execute("SELECT sum(addresses) FROM grid_density").fetchone()[0] == 10
    summary = dict(con.execute("SELECT source, addresses FROM source_summary").fetchall())
    assert summary == {"alpha": 6, "beta": 4}
    street = con.execute(
        "SELECT addresses, lowest_number, highest_number FROM street_summary WHERE source = 'alpha'"
    ).fetchone()
    assert street == (6, 100, 105)


def test_clean_data_passes_every_check(con, layout, write_gpkg):
    load(con, layout, write_gpkg, "a", n=6)
    warehouse.build(con, layout)

    results = warehouse.run_checks(con)

    assert len(results) == 7
    assert all(r.passed for r in results), [r.name for r in results if not r.passed]


def test_rebuild_is_repeatable(con, layout, write_gpkg):
    load(con, layout, write_gpkg, "a", n=6)
    warehouse.build(con, layout)
    warehouse.build(con, layout)

    assert con.execute("SELECT count(*) FROM addresses").fetchone()[0] == 6


def test_duplicate_source_id_fails_as_an_error(con, layout, write_gpkg):
    frame = make_frame(n=4)
    frame.loc[1, "source_id"] = frame.loc[0, "source_id"]
    load(con, layout, write_gpkg, "a", frame=frame)
    warehouse.build(con, layout)

    result = by_name(warehouse.run_checks(con))["unique_source_id"]

    assert not result.passed and result.severity == "error"
    assert result.sample[0]["copies"] == 2


def test_point_outside_canada_fails(con, layout, write_gpkg):
    # The contract only checks the CRS and geometry type, so a misplaced point is caught by the warehouse check.
    frame = make_frame(n=4, lon0=2.35, lat0=48.85)  # Paris
    load(con, layout, write_gpkg, "a", frame=frame)
    warehouse.build(con, layout)

    assert not by_name(warehouse.run_checks(con))["inside_canada"].passed


def test_low_parse_rate_fails(con, layout, write_gpkg):
    frame = make_frame(n=10)
    frame.loc[:2, ["parsed", "house_number"]] = [False, None]
    load(con, layout, write_gpkg, "a", frame=frame)
    warehouse.build(con, layout)

    assert not by_name(warehouse.run_checks(con))["parse_rate"].passed


def test_parsed_row_without_a_street_name_fails(con, layout, write_gpkg):
    frame = make_frame(n=5)
    frame.loc[0, "street_name"] = None
    load(con, layout, write_gpkg, "a", frame=frame)
    warehouse.build(con, layout)

    assert not by_name(warehouse.run_checks(con))["core_fields_present"].passed


def test_repeated_address_is_only_a_warning(con, layout, write_gpkg):
    frame = make_frame(n=4)
    frame.loc[1, "full_address"] = frame.loc[0, "full_address"]
    load(con, layout, write_gpkg, "a", frame=frame)
    warehouse.build(con, layout)

    result = by_name(warehouse.run_checks(con))["repeated_addresses"]

    assert not result.passed and result.severity == "warn"


def test_shrinking_reload_raises_a_volume_warning(con, layout, write_gpkg):
    load(con, layout, write_gpkg, "v1", n=20)
    load(con, layout, write_gpkg, "v2", n=10)
    warehouse.build(con, layout)

    result = by_name(warehouse.run_checks(con))["row_count_drop"]

    assert not result.passed and result.severity == "warn"
    assert result.sample[0] == {"source": "alpha", "previous_rows": 20, "current_rows": 10}


def test_growing_reload_is_fine(con, layout, write_gpkg):
    load(con, layout, write_gpkg, "v1", n=10)
    load(con, layout, write_gpkg, "v2", n=20)
    warehouse.build(con, layout)

    assert by_name(warehouse.run_checks(con))["row_count_drop"].passed


def test_check_results_are_stored(con, layout, write_gpkg):
    load(con, layout, write_gpkg, "a", n=6)
    warehouse.build(con, layout)
    warehouse.run_checks(con)

    assert con.execute("SELECT count(*) FROM check_results").fetchone()[0] == 7
