import json
import numpy as np
import pytest
from rasterio.transform import from_origin
from geosense.pipeline import analyze, csv_safe
from geosense.raster import Scene, read_scene
from geosense.run_store import list_runs, load_run
from geosense.vector_io import load_package


def test_patch_filter_removes_entire_small_scene():
    scene = Scene(
        {"mask": np.ones((2, 2), dtype="float32")},
        np.ones((2, 2), dtype=bool),
        from_origin(13, 52, 0.001, 0.001),
        "EPSG:4326",
        "tiny",
    )
    result = analyze(scene, "prepared_mask", min_pixels=9)
    assert not result.mask.any()
    assert result.report["area_km2"] == 0


@pytest.mark.parametrize("text", ["=1+1", " +SUM(A1)", "\t@command", "-formula"])
def test_csv_provider_formula_escape(text):
    assert csv_safe(text) == "'" + text
    assert csv_safe(-2.5) == -2.5
    assert csv_safe("High severity") == "High severity"


@pytest.mark.parametrize(
    "name", ["../outside.json", "C:/outside.json", "/outside.json"]
)
def test_loose_upload_path_rejected(name):
    with pytest.raises(ValueError, match="unsafe"):
        load_package([(name, b"{}")])


def test_duplicate_loose_uploads():
    with pytest.raises(ValueError, match="Duplicate"):
        load_package([("x.json", b"{}"), ("X.json", b"{}")])


def test_corrupt_library_metadata(tmp_path):
    run_id = "a" * 32
    directory = tmp_path / run_id
    directory.mkdir()
    (directory / "manifest.json").write_text(json.dumps({"run_id": run_id}))
    assert list_runs(tmp_path) == []
    with pytest.raises(ValueError, match="metadata"):
        load_run(run_id, tmp_path)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_pixels": 1.5},
        {"scale": float("nan")},
        {"mapping": {"mask": True}},
        {"scl_band": 0.5},
    ],
)
def test_bad_read_parameters_fail_before_raster_io(kwargs):
    arguments = {"mapping": {"mask": 1}, **kwargs}
    with pytest.raises(ValueError):
        read_scene(b"", **arguments)
