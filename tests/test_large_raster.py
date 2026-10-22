import numpy as np
import pytest
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from geosense.raster import read_scene, inspect_raster
from geosense.pipeline import analyze


def fixture():
    data = np.zeros((200, 300), dtype="uint8")
    data[50:150, 100:200] = 1
    with MemoryFile() as mem:
        with mem.open(
            driver="GTiff",
            height=200,
            width=300,
            count=1,
            dtype="uint8",
            crs="EPSG:32633",
            transform=from_origin(400000, 5800000, 20, 20),
        ) as dst:
            dst.write(data, 1)
        return mem.read()


def test_budget_preserves_extent_and_classes():
    payload = fixture()
    scene = read_scene(payload, {"mask": 1}, max_pixels=600)
    assert scene.valid.size <= 600
    assert scene.processing["reduced_resolution"]
    assert set(np.unique(scene.bands["mask"])) == {0, 1}
    assert scene.transform.a * scene.shape[1] == pytest.approx(6000)
    assert inspect_raster(payload)["binary_sample"]
    assert analyze(scene, "prepared_mask", min_pixels=1).mask.any()


def test_crop_before_budget_retains_native_detail():
    scene = read_scene(
        fixture(),
        {"mask": 1},
        max_pixels=10000,
        bounds=[402000, 5797000, 404000, 5799000],
    )
    assert scene.shape == (100, 100)
    assert not scene.processing["reduced_resolution"]
    assert analyze(scene, "prepared_mask", min_pixels=1).mask.all()


def test_thermal_rejects_binary_input():
    scene = read_scene(fixture(), {"thermal": 1})
    with pytest.raises(ValueError, match="Kelvin"):
        analyze(scene, "active_fire")


def test_duplicate_quality_band_rejected_before_read():
    with pytest.raises(ValueError, match="SCL"):
        read_scene(fixture(), {"thermal": 1}, scl_band=1)
