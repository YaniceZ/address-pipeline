import duckdb

from addrpipe.cli import main

from .conftest import make_frame


def run(tmp_path, *args):
    return main(["--root", str(tmp_path / "out"), *map(str, args)])


def test_run_succeeds_on_clean_input(tmp_path, write_gpkg, capsys):
    code = run(tmp_path, "run", write_gpkg("a", n=6))

    out = capsys.readouterr().out
    assert code == 0
    assert "loaded" in out and "built 4 models" in out and "pass  01_unique_source_id" in out


def test_second_run_reports_unchanged(tmp_path, write_gpkg, capsys):
    path = write_gpkg("a", n=6)
    run(tmp_path, "run", path)
    capsys.readouterr()

    assert run(tmp_path, "run", path) == 0
    assert "unchanged" in capsys.readouterr().out


def test_rejected_file_gives_exit_code_2_and_names_the_problem(tmp_path, write_gpkg, capsys):
    code = run(tmp_path, "run", write_gpkg("good", n=5), write_gpkg("bad", frame=make_frame(source="beta", province=True)))

    out = capsys.readouterr().out
    assert code == 2
    assert "rejected" in out and "column province" in out
    # The good source is still loaded and checked.
    con = duckdb.connect(str(tmp_path / "out" / "warehouse.duckdb"), read_only=True)
    assert con.execute("SELECT count(*) FROM addresses").fetchone()[0] == 5


def test_failing_check_gives_exit_code_1(tmp_path, write_gpkg, capsys):
    frame = make_frame(n=4)
    frame.loc[1, "source_id"] = frame.loc[0, "source_id"]

    assert run(tmp_path, "run", write_gpkg("dup", frame=frame)) == 1
    assert "FAIL  01_unique_source_id" in capsys.readouterr().out


def test_only_rejected_input_does_not_crash(tmp_path, write_gpkg, capsys):
    code = run(tmp_path, "run", write_gpkg("bad", frame=make_frame(province=True)))

    assert code == 2
    assert "run ingest first" in capsys.readouterr().out


def test_status_lists_loads_and_sources(tmp_path, write_gpkg, capsys):
    run(tmp_path, "run", write_gpkg("a", n=6))
    capsys.readouterr()

    assert run(tmp_path, "status") == 0
    out = capsys.readouterr().out
    assert "Recent loads" in out and "Sources in the warehouse" in out and "6 addresses" in out
