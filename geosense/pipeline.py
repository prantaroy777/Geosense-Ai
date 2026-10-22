"""Shared analysis, AOI masking, area calculation and portable exports."""

from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
import json
import zipfile
import csv
import hashlib
import numpy as np
from pyproj import Geod
from rasterio.features import geometry_mask, shapes
from scipy.ndimage import label
from . import __version__
from rasterio.io import MemoryFile
from rasterio.warp import transform_geom
from shapely.geometry import shape
from shapely.geometry.polygon import orient
from .detectors import REGISTRY
from .raster import align_scene


@dataclass
class Result:
    score: np.ndarray
    mask: np.ndarray
    valid: np.ndarray
    features: dict
    report: dict
    scene: object


def aoi_mask(aoi, scene):
    if "crs" in aoi:
        raise ValueError(
            "AOI must be RFC 7946 GeoJSON in WGS84, without a legacy CRS member."
        )
    kind = aoi.get("type")
    geometries = (
        [f.get("geometry") for f in aoi.get("features", [])]
        if kind == "FeatureCollection"
        else [aoi.get("geometry")]
        if kind == "Feature"
        else [aoi]
    )
    if not geometries:
        raise ValueError("AOI contains no polygons.")
    projected = []
    for geometry in geometries:
        if not geometry or geometry.get("type") not in ("Polygon", "MultiPolygon"):
            raise ValueError("AOI must contain only Polygon or MultiPolygon geometry.")
        polygon = shape(geometry)
        if polygon.is_empty or not polygon.is_valid:
            raise ValueError("AOI contains an empty or invalid polygon.")
        minx, miny, maxx, maxy = polygon.bounds
        if minx < -180 or maxx > 180 or miny < -90 or maxy > 90:
            raise ValueError("AOI coordinates must be WGS84 longitude/latitude.")
        projected.append(transform_geom("EPSG:4326", scene.crs, geometry))
    return geometry_mask(
        projected, out_shape=scene.shape, transform=scene.transform, invert=True
    )


def analyze(after, detector_id, before=None, threshold=None, aoi=None, min_pixels=9):
    detector = REGISTRY[detector_id]
    threshold = detector.threshold if threshold is None else float(threshold)
    lower, upper = (
        (150, 500)
        if detector_id == "active_fire"
        else ((-1e9, 1e9) if detector_id == "prepared_mask" else (-2, 2))
    )
    if not np.isfinite(threshold) or not lower <= threshold <= upper:
        raise ValueError(f"Threshold must be finite and between {lower} and {upper}.")
    if not isinstance(min_pixels, int) or min_pixels < 1:
        raise ValueError("Minimum patch size must be a positive integer.")
    if detector.needs_before and before is None:
        raise ValueError("This detector requires both a before and an after scene.")
    scenes = [after] + ([before] if detector.needs_before else [])
    for scene in scenes:
        missing = set(detector.bands) - scene.bands.keys()
        if missing:
            raise ValueError(
                f"{scene.name}: missing bands: {', '.join(sorted(missing))}"
            )
    if detector_id == "active_fire":
        values = after.bands["thermal"][after.valid]
        if values.size and (np.nanmedian(values) < 150 or np.nanmedian(values) > 500):
            raise ValueError(
                "Thermal analysis requires brightness temperature in Kelvin. This band does not look like Kelvin data. For a 0/1 event raster, choose Existing event mask."
            )
    if detector.needs_before:
        before = align_scene(before, after)
    valid = after.valid.copy()
    if detector.needs_before:
        valid &= before.valid
    if aoi is not None:
        valid &= aoi_mask(aoi, after)
    score, selected = detector.evaluate(
        after.bands, before.bands if before else None, threshold
    )
    valid &= np.isfinite(score)
    if not valid.any():
        raise ValueError(
            "No valid pixels remain. Check scene overlap, AOI, nodata and quality masks."
        )
    mask = selected & valid
    # Count eight-connected candidates; never fill holes or retain isolated islands.
    if min_pixels > 1 and mask.any():
        components, _ = label(mask, structure=np.ones((3, 3), dtype=bool))
        sizes = np.bincount(components.ravel())
        mask &= sizes[components] >= min_pixels
    score = np.where(valid, score, np.nan).astype("float32")
    geod = Geod(ellps="WGS84")
    features = []
    for geometry, value in shapes(
        mask.astype("uint8"), mask=mask, transform=after.transform
    ):
        geographic = transform_geom(after.crs, "EPSG:4326", geometry, precision=10)
        area = abs(geod.geometry_area_perimeter(orient(shape(geographic), sign=1.0))[0])
        features.append(
            {
                "type": "Feature",
                "geometry": geographic,
                "properties": {
                    "id": len(features) + 1,
                    "analysis": detector_id,
                    "area_m2": area,
                },
            }
        )
    report = {
        "application": "GeoSense AI",
        "version": __version__,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "detector": detector_id,
        "method": detector.score_name,
        "threshold": threshold,
        "minimum_patch_pixels": min_pixels,
        "after": after.name,
        "before": before.name if detector.needs_before else None,
        "crs": str(after.crs),
        "valid_pixels": int(valid.sum()),
        "detected_pixels": int(mask.sum()),
        "detected_fraction_of_valid": float(mask.sum() / valid.sum()),
        "area_km2": sum(f["properties"]["area_m2"] for f in features) / 1e6,
        "polygon_count": len(features),
        "limitations": detector.description,
        "synthetic": after.synthetic
        or (before.synthetic if detector.needs_before else False),
        "aoi_applied": aoi is not None,
    }
    report["processing"] = after.processing
    report["baseline_processing"] = before.processing if detector.needs_before else None
    result = Result(
        score,
        mask,
        valid,
        {"type": "FeatureCollection", "features": features},
        report,
        after,
    )
    from .science import interpretation, class_statistics

    classes, labels, _ = interpretation(result)
    report["class_statistics"] = class_statistics(classes, after, labels)
    report["analysis_id"] = hashlib.sha256(
        score.tobytes()
        + json.dumps(
            {
                k: report[k]
                for k in ["detector", "threshold", "minimum_patch_pixels", "crs"]
            },
            sort_keys=True,
        ).encode()
        + str(after.transform).encode()
    ).hexdigest()[:16]
    return result


def raster_bytes(result, score=False):
    data = (
        result.score
        if score
        else np.where(result.valid, result.mask.astype("uint8"), 255).astype("uint8")
    )
    with MemoryFile() as mem:
        with mem.open(
            driver="GTiff",
            height=data.shape[0],
            width=data.shape[1],
            count=1,
            dtype=str(data.dtype),
            crs=result.scene.crs,
            transform=result.scene.transform,
            nodata=np.nan if score else 255,
            compress="deflate",
        ) as dst:
            dst.write(data, 1)
            dst.set_band_description(
                1,
                result.report["method"]
                if score
                else "0=unselected, 1=candidate, 255=invalid",
            )
        return mem.read()


def map_bytes(result, extension="png", metadata=None, context=None):
    from .cartography import map_bytes as render

    return render(result, extension, metadata, context)


def export_bundle(result, metadata=None, context=None):
    from .reporting import research_report
    from .science import interpretation
    from io import StringIO

    if metadata is not None:
        result.report["presentation"] = metadata
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("candidate_mask.tif", raster_bytes(result))
        archive.writestr("analysis_score.tif", raster_bytes(result, score=True))
        archive.writestr(
            "candidate_areas.geojson", json.dumps(result.features, indent=2)
        )
        archive.writestr("report.json", json.dumps(result.report, indent=2))
        archive.writestr("map.png", map_bytes(result, context=context))
        map_pdf = map_bytes(result, "pdf", context=context)
        archive.writestr("map.pdf", map_pdf)
        archive.writestr("research_report.pdf", research_report(result, map_pdf))
        classes, labels, _ = interpretation(result)
        with MemoryFile() as mem:
            with mem.open(
                driver="GTiff",
                height=classes.shape[0],
                width=classes.shape[1],
                count=1,
                dtype="uint8",
                crs=result.scene.crs,
                transform=result.scene.transform,
                nodata=255,
                compress="deflate",
            ) as dst:
                dst.write(classes, 1)
                dst.update_tags(class_legend=json.dumps(dict(enumerate(labels))))
            archive.writestr("mapped_classes.tif", mem.read())
        table = StringIO()
        writer = csv.DictWriter(
            table, fieldnames=["class", "label", "pixels", "area_km2", "area_percent"]
        )
        writer.writeheader()
        writer.writerows(
            {key: csv_safe(value) for key, value in row.items()}
            for row in result.report["class_statistics"]
        )
        archive.writestr("class_statistics.csv", table.getvalue())
        if context:
            archive.writestr("context.geojson", json.dumps(context))
        if result.report.get("vector_product"):
            archive.writestr(
                "README.txt",
                "Event polygons and their attributes are in candidate_areas.geojson. Areas are measured on vector unions. All TIFFs are cartographic derivatives only. Imported classes are supplied by the provider, not newly detected. Review report.json for exclusions and presentation limits.",
            )
    return output.getvalue()


def csv_safe(value):
    """Keep provider text from becoming a formula when CSV is opened in a spreadsheet."""
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value
