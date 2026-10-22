import json
from io import BytesIO
from zipfile import ZipFile
from shapely.geometry import box
import pytest
from geosense.monitoring import collection, compare_products, demo_products
from geosense.quality import vector_quality
from geosense.run_store import save_run, list_runs, load_run


def test_comparison_partitions_and_dates():
    before, current, bc, cc = demo_products()
    changes, coverage, report = compare_products(
        before, current, bc, cc, "2025-08-01", "2025-08-15"
    )
    rows = {r["change"]: r["area_km2"] for r in report["classes"]}
    assert len(changes["features"]) == 3
    assert rows["Newly mapped"] > 0
    assert rows["No longer mapped"] > 0
    assert report["current_event_km2"] == pytest.approx(
        rows["Newly mapped"] + rows["Persistent"], rel=1e-6
    )
    with pytest.raises(ValueError, match="later"):
        compare_products(before, current, bc, cc, "2025-08-15", "2025-08-01")


def test_coverage_loss_is_not_disappearance():
    events = collection(box(13, 52, 13.02, 52.02))
    coverage = collection(box(13, 52, 13.02, 52.02))
    reduced = collection(box(13, 52, 13.01, 52.02))
    _, _, report = compare_products(
        events, events, coverage, reduced, "2025-01-01", "2025-01-02"
    )
    assert (
        next(
            r["area_km2"]
            for r in report["classes"]
            if r["change"] == "No longer mapped"
        )
        == 0
    )
    assert report["reference_only_coverage_km2"] > 0


def test_empty_events_and_no_shared_coverage():
    empty = {"type": "FeatureCollection", "features": []}
    coverage = collection(box(13, 52, 13.02, 52.02))
    changes, _, report = compare_products(
        empty, empty, coverage, coverage, "2025-01-01", "2025-01-02"
    )
    assert not changes["features"]
    assert report["percent_change"] is None
    with pytest.raises(ValueError, match="shared"):
        compare_products(
            empty,
            empty,
            coverage,
            collection(box(14, 52, 14.02, 52.02)),
            "2025-01-01",
            "2025-01-02",
        )


def test_quality_duplicates_and_unverified_accuracy():
    doc = collection(box(13, 52, 13.01, 52.01))
    doc["features"] *= 2
    quality = vector_quality(doc, {"invalid_skipped": 2})
    assert quality["status"] == "review_required"
    assert not quality["accuracy_verified"]
    assert (
        next(
            f["status"]
            for f in quality["findings"]
            if f["check"] == "Duplicate geometries"
        )
        == "warning"
    )


def test_saved_run_integrity_and_path(tmp_path):
    output = BytesIO()
    with ZipFile(output, "w") as z:
        z.writestr("report.json", json.dumps({"analysis_id": "abc", "method": "test"}))
    saved = save_run(output.getvalue(), "Test", tmp_path)
    assert len(list_runs(tmp_path)) == 1
    assert load_run(saved["run_id"], tmp_path)[1] == output.getvalue()
    with pytest.raises(ValueError, match="identifier"):
        load_run("../escape", tmp_path)
    (tmp_path / saved["run_id"] / "results.zip").write_bytes(b"changed")
    with pytest.raises(ValueError, match="integrity"):
        load_run(saved["run_id"], tmp_path)
