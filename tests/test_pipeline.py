import json
from io import BytesIO
from zipfile import ZipFile
import numpy as np
import pytest
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from geosense.demo import demo_scenes, scene_bytes
from geosense.detectors import REGISTRY, normalized
from geosense.pipeline import analyze, export_bundle
from geosense.raster import read_scene, align_scene, Scene


@pytest.mark.parametrize("detector", REGISTRY)
def test_demo_detectors_have_candidates_and_exclude_invalid(detector):
    before, after = demo_scenes()
    result = analyze(after, detector, before)
    assert result.mask.any()
    assert not result.mask[:5].any()
    assert result.report["area_km2"] > 0
    assert result.features["features"]


def test_flood_excludes_permanent_water():
    before, after = demo_scenes()
    result = analyze(after, "flood", before)
    assert not result.mask[110:140, 10:70].any()
    assert result.mask[100:140, 90:160].all()
    assert result.report["detected_pixels"] == 2800
    assert result.report["area_km2"] == pytest.approx(1.12, rel=0.01)


def test_missing_data_and_zero_denominator():
    _, after = demo_scenes()
    with pytest.raises(ValueError, match="both"):
        analyze(after, "burned_area")
    after.bands.pop("nir")
    with pytest.raises(ValueError, match="missing bands"):
        analyze(after, "forest_stress")
    assert np.isnan(normalized(np.zeros(1), np.zeros(1))).all()


def test_roundtrip_and_export():
    before, after = demo_scenes()
    loaded = read_scene(scene_bytes(after), {"nir": 3, "swir2": 5})
    assert loaded.synthetic
    result = analyze(loaded, "burned_area", before)
    with ZipFile(BytesIO(export_bundle(result))) as archive:
        assert set(archive.namelist()) == {
            "candidate_mask.tif",
            "analysis_score.tif",
            "candidate_areas.geojson",
            "report.json",
            "map.png",
            "map.pdf",
            "mapped_classes.tif",
            "class_statistics.csv",
            "research_report.pdf",
        }
        with (
            MemoryFile(archive.read("candidate_mask.tif")) as mem,
            mem.open() as raster,
        ):
            assert raster.crs == after.crs
            assert raster.nodata == 255
            assert (raster.read(1)[:5] == 255).all()
        assert json.loads(archive.read("report.json"))["detected_pixels"] == 3000
        assert archive.read("map.pdf").startswith(b"%PDF")


def test_alignment_and_no_overlap():
    before, after = demo_scenes()
    shifted = Scene(
        before.bands,
        before.valid,
        from_origin(900000, 5800000, 20, 20),
        before.crs,
        "far away",
    )
    aligned = align_scene(shifted, after)
    assert not aligned.valid.any()
    with pytest.raises(ValueError, match="No valid pixels"):
        analyze(after, "burned_area", shifted)


def test_aoi_clips_and_rejects_non_polygon():
    from rasterio.warp import transform_geom

    before, after = demo_scenes()
    polygon = {
        "type": "Polygon",
        "coordinates": [
            [
                [400000, 5800000],
                [402000, 5800000],
                [402000, 5796800],
                [400000, 5796800],
                [400000, 5800000],
            ]
        ],
    }
    aoi = transform_geom(after.crs, "EPSG:4326", polygon)
    result = analyze(after, "flood", before, aoi=aoi)
    assert result.report["detected_pixels"] == 400
    with pytest.raises(ValueError, match="Polygon"):
        analyze(after, "waterbody", aoi={"type": "Point", "coordinates": [13, 52]})


def test_zero_candidates_is_valid_result():
    before, after = demo_scenes()
    result = analyze(after, "burned_area", before, threshold=2)
    assert result.report["area_km2"] == 0
    assert result.features["features"] == []
