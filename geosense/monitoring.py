"""Coverage-aware vector monitoring; map revisions are not causal attribution."""

from datetime import date
from shapely.geometry import shape, mapping
from shapely.ops import unary_union
from .vector_analysis import geodesic_area, vector_result


def polygon_union(document, label, allow_empty=False):
    geometries = []
    for feature in document.get("features", []):
        geom = shape(feature["geometry"])
        if geom.is_empty or not geom.is_valid:
            raise ValueError(
                f"{label}: invalid or empty geometry must be reviewed before comparison."
            )
        if geom.geom_type not in ("Polygon", "MultiPolygon"):
            raise ValueError(f"{label}: polygon geometry is required.")
        geometries.append(geom)
    if not geometries and not allow_empty:
        raise ValueError(f"{label}: no coverage polygons supplied.")
    result = unary_union(geometries)
    if not result.is_empty and result.bounds[2] - result.bounds[0] > 180:
        raise ValueError(
            "Antimeridian-spanning comparisons require a dedicated projection."
        )
    return result


def collection(geometry, properties=None):
    return {
        "type": "FeatureCollection",
        "features": []
        if geometry.is_empty
        else [
            {
                "type": "Feature",
                "properties": properties or {},
                "geometry": mapping(geometry),
            }
        ],
    }


def compare_products(
    before, current, before_coverage, current_coverage, before_date, current_date
):
    start, end = (
        date.fromisoformat(str(before_date)),
        date.fromisoformat(str(current_date)),
    )
    if end <= start:
        raise ValueError(
            "The current observation date must be later than the reference observation date."
        )
    coverage_b = polygon_union(before_coverage, "Reference coverage")
    coverage_c = polygon_union(current_coverage, "Current coverage")
    shared = coverage_b.intersection(coverage_c)
    if shared.is_empty or geodesic_area(shared) <= 0:
        raise ValueError("No shared surveyed area; these products cannot be compared.")
    b = polygon_union(before, "Reference events", allow_empty=True).intersection(shared)
    c = polygon_union(current, "Current events", allow_empty=True).intersection(shared)
    geometries = {
        "Newly mapped": c.difference(b),
        "Persistent": c.intersection(b),
        "No longer mapped": b.difference(c),
    }
    features = []
    rows = []
    for label, geom in geometries.items():
        rows.append({"change": label, "area_km2": geodesic_area(geom) / 1e6})
        features.extend(collection(geom, {"change": label})["features"])
    before_area, current_area = geodesic_area(b) / 1e6, geodesic_area(c) / 1e6
    summary = {
        "reference_date": start.isoformat(),
        "current_date": end.isoformat(),
        "elapsed_days": (end - start).days,
        "common_coverage_km2": geodesic_area(shared) / 1e6,
        "reference_only_coverage_km2": geodesic_area(coverage_b.difference(shared))
        / 1e6,
        "current_only_coverage_km2": geodesic_area(coverage_c.difference(shared)) / 1e6,
        "reference_event_km2": before_area,
        "current_event_km2": current_area,
        "net_change_km2": current_area - before_area,
        "percent_change": (current_area - before_area) / before_area * 100
        if before_area
        else None,
        "classes": rows,
        "interpretation": "Changes are differences between mapped polygon products inside shared survey coverage. No longer mapped does not establish recovery. Differences can reflect timing, source resolution, digitisation, classification or producer revisions. No positional tolerance or statistical significance model is applied.",
    }
    return (
        {"type": "FeatureCollection", "features": features},
        collection(shared),
        summary,
    )


def monitoring_result(
    before, current, before_coverage, current_coverage, before_date, current_date
):
    changes, coverage, summary = compare_products(
        before, current, before_coverage, current_coverage, before_date, current_date
    )
    if not changes["features"]:
        return None, coverage, summary
    result = vector_result(changes, "Monitoring comparison", coverage, "change")
    result.report["monitoring"] = summary
    result.report["method"] = "Coverage-aware polygon change"
    result.report["limitations"] = summary["interpretation"]
    result.report["before"] = "Reference mapped product"
    colors = {
        "Outside selected event": "#edf0eb",
        "Newly mapped": "#bd463a",
        "Persistent": "#e0b04d",
        "No longer mapped": "#45879c",
    }
    result.report["display_colors"] = [
        colors[label] for label in result.report["display_labels"]
    ]
    return result, coverage, summary


def demo_products():
    from shapely.geometry import box

    return (
        collection(box(13, 52, 13.03, 52.03)),
        collection(box(13.01, 52, 13.04, 52.03)),
        collection(box(12.99, 51.99, 13.05, 52.04)),
        collection(box(12.99, 51.99, 13.05, 52.04)),
    )
