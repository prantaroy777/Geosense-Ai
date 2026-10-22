"""Inspectable quality findings; checks are not a certification of accuracy."""

from shapely.geometry import shape
from shapely.ops import unary_union
from .vector_analysis import geodesic_area


def vector_quality(document, evidence, attribution="", observation_date=""):
    features = document.get("features", [])
    geometries = [shape(f["geometry"]) for f in features]
    polygonal = all(g.geom_type in ("Polygon", "MultiPolygon") for g in geometries)
    discarded = evidence.get("invalid_skipped", 0) + evidence.get("empty_skipped", 0)
    duplicates = len(geometries) - len({g.normalize().wkb for g in geometries})
    overlap = 0.0
    if polygonal and geometries:
        overlap = max(
            0.0,
            (
                sum(geodesic_area(g) for g in geometries)
                - geodesic_area(unary_union(geometries))
            )
            / 1e6,
        )
    findings = [
        {
            "check": "Readable features",
            "status": "pass" if features else "fail",
            "detail": f"{len(features):,} retained features",
        },
        {
            "check": "Event geometry",
            "status": "pass" if polygonal else "fail",
            "detail": "Polygon/MultiPolygon required for area comparisons",
        },
        {
            "check": "Excluded geometries",
            "status": "warning" if discarded else "pass",
            "detail": f"{discarded} invalid/empty geometries excluded by the importer",
        },
        {
            "check": "Duplicate geometries",
            "status": "warning" if duplicates else "pass",
            "detail": f"{duplicates} exact normalized duplicates; union measurements avoid double counting",
        },
        {
            "check": "Overlapping area",
            "status": "warning" if overlap > 1e-6 else "pass",
            "detail": f"{overlap:.6f} km² summed-feature excess over union area",
        },
        {
            "check": "Observation date",
            "status": "pass" if observation_date else "warning",
            "detail": str(observation_date)
            or "Not supplied; do not infer observation date from file modification time",
        },
        {
            "check": "Source attribution",
            "status": "pass" if attribution.strip() else "warning",
            "detail": attribution.strip() or "Not supplied",
        },
        {
            "check": "Scientific accuracy",
            "status": "unverified",
            "detail": "Import and geometry checks do not validate event interpretation or positional accuracy",
        },
    ]
    return {
        "status": "fail"
        if any(x["status"] == "fail" for x in findings)
        else "review_required"
        if any(x["status"] == "warning" for x in findings)
        else "technical_checks_passed",
        "findings": findings,
        "accuracy_verified": False,
    }
