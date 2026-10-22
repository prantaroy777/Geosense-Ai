"""Explicit scientific interpretations and independent-reference comparison."""

import numpy as np
from pyproj import Geod
from rasterio.features import shapes
from rasterio.warp import transform_geom
from shapely.geometry import shape
from shapely.geometry.polygon import orient

SEVERITY_SOURCE = "https://forest-fire.emergency.copernicus.eu/about-effis/technical-background/fire-severity"
SEVERITY_LABELS = [
    "Unburned / regrowth",
    "Low severity",
    "Moderate-low severity",
    "Moderate-high severity",
    "High severity",
]
SEVERITY_COLORS = ["#cddbc9", "#f9df83", "#f5a641", "#e56b37", "#a51e36"]
SEVERITY_BREAKS = [0.10, 0.27, 0.44, 0.66]


def severity_classes(score, valid):
    """EFFIS reference thresholds; bins are lower-inclusive, upper-exclusive."""
    edges = np.asarray(SEVERITY_BREAKS, dtype=score.dtype)
    return np.where(valid & np.isfinite(score), np.digitize(score, edges), 255).astype(
        "uint8"
    )


def class_statistics(classes, scene, labels):
    areas = np.zeros(len(labels), dtype=float)
    geod = Geod(ellps="WGS84")
    for geometry, value in shapes(
        classes, mask=classes != 255, transform=scene.transform
    ):
        polygon = shape(transform_geom(scene.crs, "EPSG:4326", geometry))
        areas[int(value)] += abs(
            geod.geometry_area_perimeter(orient(polygon, sign=1))[0]
        )
    total = areas.sum()
    return [
        {
            "class": i,
            "label": label,
            "pixels": int(np.sum(classes == i)),
            "area_km2": float(areas[i] / 1e6),
            "area_percent": float(100 * areas[i] / total) if total else 0,
        }
        for i, label in enumerate(labels)
    ]


def interpretation(result):
    if result.report.get("vector_product"):
        return (
            np.where(result.valid, result.score, 255).astype("uint8"),
            result.report["display_labels"],
            result.report["display_colors"],
        )
    if result.report["detector"] == "burned_area":
        classes = severity_classes(result.score, result.valid)
        return classes, SEVERITY_LABELS, SEVERITY_COLORS
    classes = np.where(result.valid, result.mask, 255).astype("uint8")
    return (
        classes,
        ["Other valid pixels", "Selected / candidate area"],
        ["#e3e9e6", "#c8413c"],
    )


def compare_reference(result, reference, positive_class=1):
    """Reference is categorical and must align exactly; never interpolate class IDs."""
    from rasterio.warp import reproject, Resampling

    source = reference.bands["mask"]
    aligned = np.full(result.valid.shape, np.nan, dtype="float32")
    reproject(
        source,
        aligned,
        src_transform=reference.transform,
        src_crs=reference.crs,
        dst_transform=result.scene.transform,
        dst_crs=result.scene.crs,
        src_nodata=np.nan,
        dst_nodata=np.nan,
        resampling=Resampling.nearest,
    )
    valid = result.valid & np.isfinite(aligned)
    if not valid.any():
        raise ValueError("Reference labels do not overlap valid analysis pixels.")
    truth = aligned[valid] == positive_class
    prediction = result.mask[valid]
    tp = int(np.sum(truth & prediction))
    fp = int(np.sum(~truth & prediction))
    fn = int(np.sum(truth & ~prediction))
    tn = int(np.sum(~truth & ~prediction))

    def divide(a, b):
        return float(a / b) if b else None

    return {
        "reference": reference.name,
        "positive_class": positive_class,
        "evaluated_pixels": int(valid.sum()),
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "true_negative": tn,
        "precision": divide(tp, tp + fp),
        "recall": divide(tp, tp + fn),
        "f1": divide(2 * tp, 2 * tp + fp + fn),
        "iou": divide(tp, tp + fp + fn),
        "note": "Pixel agreement on the processed grid. Independent, representative reference labels are required; agreement with derived or training labels is not independent validation.",
    }
