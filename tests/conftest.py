import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point

from addrpipe import warehouse
from addrpipe.warehouse import Layout


def make_frame(source="alpha", n=5, province="BC", start_id=1, lon0=-123.0, lat0=49.0) -> gpd.GeoDataFrame:
    """A small frame that satisfies the contract."""
    rows = [
        {
            "source": source,
            "source_id": start_id + i,
            "house_number": str(100 + i),
            "number_suffix": None,
            "unit": None,
            "street_name": "MAIN",
            "street_type": "ST",
            "street_dir": None,
            "full_address": f"{100 + i} MAIN ST",
            "city": "TESTVILLE",
            "province": province,
            "parsed": True,
            "raw_street_type": "ST",
        }
        for i in range(n)
    ]
    frame = pd.DataFrame(rows)
    points = [Point(lon0 + i * 0.001, lat0 + i * 0.001) for i in range(n)]
    return gpd.GeoDataFrame(frame, geometry=points, crs="EPSG:4326")


@pytest.fixture
def write_gpkg(tmp_path):
    def write(name: str, frame: gpd.GeoDataFrame | None = None, **kwargs):
        path = tmp_path / "inputs" / f"{name}.gpkg"
        path.parent.mkdir(exist_ok=True)
        (frame if frame is not None else make_frame(**kwargs)).to_file(path, layer="civic_address", driver="GPKG")
        return path

    return write


@pytest.fixture
def layout(tmp_path) -> Layout:
    return Layout(tmp_path / "out")


@pytest.fixture
def con(layout):
    connection = warehouse.connect(layout)
    yield connection
    connection.close()
