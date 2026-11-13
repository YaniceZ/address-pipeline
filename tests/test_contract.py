import pytest

from addrpipe.contract import ContractError, validate

from .conftest import make_frame


def violations(frame) -> list[str]:
    with pytest.raises(ContractError) as caught:
        validate(frame)
    return caught.value.violations


def test_valid_frame_passes():
    validate(make_frame())


def test_boolean_province_is_rejected():
    # The real bug that motivated this check: YAML turned province ON into True.
    frame = make_frame(province=True)
    assert any("column province" in v and "bool" in v for v in violations(frame))


def test_province_must_be_a_two_letter_code():
    assert any("two-letter" in v for v in violations(make_frame(province="Ontario")))


def test_wrong_crs_is_rejected():
    frame = make_frame().to_crs("EPSG:3857")
    assert any("crs" in v for v in violations(frame))


def test_missing_and_unexpected_columns_are_reported():
    frame = make_frame().drop(columns=["city"])
    frame["surprise"] = 1
    found = violations(frame)
    assert any("missing columns: city" in v for v in found)
    assert any("unexpected columns: surprise" in v for v in found)


def test_empty_file_is_rejected():
    assert any("no rows" in v for v in violations(make_frame(n=0)))


def test_file_must_hold_one_source():
    frame = make_frame(n=4)
    frame.loc[0, "source"] = "beta"
    assert any("exactly one source" in v for v in violations(frame))


@pytest.mark.parametrize("name", ["../evil", "Has Space", "UPPER", ""])
def test_source_name_cannot_escape_the_lake(name):
    assert any("source" in v for v in violations(make_frame(source=name)))


def test_every_violation_is_listed_at_once():
    frame = make_frame(province=True).to_crs("EPSG:3857")
    assert len(violations(frame)) >= 2
