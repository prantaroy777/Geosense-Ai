from io import BytesIO
import numpy as np
import pytest
from pypdf import PdfReader
from geosense.demo import demo_scenes
from geosense.pipeline import analyze, map_bytes
from geosense.science import severity_classes, compare_reference
from geosense.reporting import research_report
from geosense.cartography import context_features


def test_severity_boundaries_and_nodata():
    scores = np.array([[-0.2, 0.099, 0.1, 0.27, 0.44, 0.66, np.nan]], dtype="float32")
    classes = severity_classes(scores, np.isfinite(scores))
    assert classes.tolist() == [[0, 0, 1, 2, 3, 4, 255]]


def test_reference_confusion_counts():
    before, after = demo_scenes()
    result = analyze(after, "burned_area", before)
    reference = demo_scenes()[1]
    metrics = compare_reference(result, reference)
    assert metrics["true_positive"] == 3000
    assert metrics["false_positive"] == 0
    assert metrics["f1"] == 1
    reference.bands["mask"][30, 35] = 0
    assert compare_reference(result, reference)["false_positive"] == 1


def test_report_provenance_and_classes():
    before, after = demo_scenes()
    result = analyze(after, "burned_area", before)
    result.report["presentation"] = {
        "title": "Synthetic research demonstration",
        "author": "Test researcher",
    }
    assert (
        sum(row["pixels"] for row in result.report["class_statistics"])
        == result.report["valid_pixels"]
    )
    report = research_report(result, map_bytes(result, "pdf"))
    pages = PdfReader(BytesIO(report)).pages
    assert len(pages) >= 3
    text = " ".join(page.extract_text() for page in pages)
    assert "Test researcher" in text
    assert "No independent reference" in text
    assert "Moderate-high severity" in text
    assert "not fire intensity" in text


def test_context_rejects_projected_geojson():
    with pytest.raises(ValueError, match="WGS84"):
        context_features(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [400000, 5800000]},
            }
        )
