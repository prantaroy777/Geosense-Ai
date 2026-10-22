"""Analyse supplied event polygons without substituting a raster area estimate."""

from . import __version__
from datetime import datetime, timezone
import hashlib
import json
import numpy as np
from pyproj import Geod
from shapely.geometry import shape, mapping
from shapely.geometry.polygon import orient
from shapely.ops import unary_union
from rasterio.crs import CRS
from rasterio.features import rasterize
from rasterio.transform import from_bounds
from .pipeline import Result
from .raster import Scene


def geodesic_area(geometry):
    if geometry.is_empty:
        return 0.0
    if geometry.geom_type == "Polygon":
        return abs(
            Geod(ellps="WGS84").geometry_area_perimeter(orient(geometry, sign=1))[0]
        )
    if hasattr(geometry, "geoms"):
        return sum(geodesic_area(g) for g in geometry.geoms)
    return 0.0


def vector_result(document, name, aoi=None, class_field=None, selected_values=None):
    boundary = None
    if aoi:
        polys = [shape(f["geometry"]) for f in aoi["features"]]
        if not polys or any(
            g.geom_type not in ["Polygon", "MultiPolygon"] for g in polys
        ):
            raise ValueError("Study-area layer must contain polygons only.")
        boundary = unary_union(polys)
    features, groups = [], {}
    for feature in document["features"]:
        geometry = shape(feature["geometry"])
        if geometry.geom_type not in ["Polygon", "MultiPolygon"]:
            raise ValueError(
                "Event area analysis requires Polygon/MultiPolygon features. Use lines and points as context."
            )
        label = (
            str(feature["properties"].get(class_field, "Unspecified"))
            if class_field
            else "Supplied event area"
        )
        if selected_values is not None and label not in selected_values:
            continue
        if boundary is not None:
            geometry = geometry.intersection(boundary)
        if geometry.is_empty or geodesic_area(geometry) == 0:
            continue
        features.append(
            {
                "type": "Feature",
                "properties": dict(feature["properties"]),
                "geometry": mapping(geometry),
            }
        )
        groups.setdefault(label, []).append(geometry)
    if not features:
        raise ValueError(
            "No event polygons remain after class selection and study-area clipping."
        )
    if len(groups) > 6:
        raise ValueError(
            "Select a field with at most 6 classes or filter its values. IDs are not useful map classes."
        )
    union = unary_union([shape(f["geometry"]) for f in features])
    extent = boundary if boundary is not None else union
    west, south, east, north = extent.bounds
    if east - west > 180:
        raise ValueError(
            "Antimeridian-spanning data needs a dedicated projection; subset the layer first."
        )
    dx, dy = (east - west) * 0.04, (north - south) * 0.04
    west, south, east, north = (
        max(-180, west - dx),
        max(-90, south - dy),
        min(180, east + dx),
        min(90, north + dy),
    )
    width, height = (
        1000,
        max(100, min(1400, int(1000 * (north - south) / (east - west)))),
    )
    transform = from_bounds(west, south, east, north, width, height)
    labels = ["Outside selected event"] + sorted(groups)
    colors = ["#edf0eb"] + [
        "#bd463a",
        "#e69647",
        "#e8c566",
        "#7aa68b",
        "#426a8b",
        "#815a98",
        "#a66b74",
        "#749b9d",
        "#7d815b",
        "#ac8466",
        "#657985",
        "#b48aab",
    ][: len(groups)]
    lookup = {label: i for i, label in enumerate(labels)}
    display = rasterize(
        [
            (mapping(g), lookup[label])
            for label in sorted(groups)
            for g in groups[label]
        ],
        out_shape=(height, width),
        transform=transform,
        fill=0,
        dtype="uint8",
    )
    valid = np.ones((height, width), dtype=bool)
    if boundary is not None:
        valid = rasterize(
            [(mapping(boundary), 1)],
            out_shape=(height, width),
            transform=transform,
            fill=0,
        ).astype(bool)
    score = np.where(valid, display, np.nan).astype("float32")
    scene = Scene({"mask": score}, valid, transform, CRS.from_epsg(4326), name)
    total = geodesic_area(union) / 1e6
    stats = [
        {
            "class": lookup[label],
            "label": label,
            "pixels": int(np.sum(display == lookup[label])),
            "area_km2": geodesic_area(unary_union(geometries)) / 1e6,
            "area_percent": geodesic_area(unary_union(geometries)) / 1e6 / total * 100,
        }
        for label, geometries in groups.items()
    ]
    report = {
        "application": "GeoSense AI",
        "version": __version__,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "detector": "prepared_mask",
        "method": "Supplied event polygons",
        "threshold": 1,
        "minimum_patch_pixels": 1,
        "after": name,
        "before": None,
        "crs": "EPSG:4326",
        "valid_pixels": int(valid.sum()),
        "detected_pixels": int(np.sum((display > 0) & valid)),
        "detected_fraction_of_valid": float(
            np.sum((display > 0) & valid) / valid.sum()
        ),
        "area_km2": total,
        "polygon_count": len(features),
        "synthetic": False,
        "aoi_applied": aoi is not None,
        "limitations": "Imported provider interpretation, not a new satellite detection. Areas use the union of source polygons, including holes, with WGS84 geodesic measurement. Display raster is visualization only. Cross-class overlaps can make class totals exceed the union total. Supplied class labels do not establish fire intensity.",
        "vector_product": True,
        "class_field": class_field,
        "display_labels": labels,
        "display_colors": colors,
        "class_statistics": stats,
        "processing": None,
        "baseline_processing": None,
        "analysis_id": hashlib.sha256(
            json.dumps(features, sort_keys=True).encode()
        ).hexdigest()[:16],
    }
    return Result(
        score,
        (display > 0) & valid,
        valid,
        {"type": "FeatureCollection", "features": features},
        report,
        scene,
    )


def context_summary(document, event_features):
    union = unary_union([shape(f["geometry"]) for f in event_features["features"]])
    intersecting = sum(
        shape(f["geometry"]).intersects(union) for f in document["features"]
    )
    return {
        "features": len(document["features"]),
        "intersecting_event": int(intersecting),
        "interpretation": "Spatial intersection only; not a confirmed damaged asset count.",
    }
