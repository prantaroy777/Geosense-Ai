"""Publication layout shared by the browser preview and PDF report."""

from io import BytesIO
import textwrap
import numpy as np
from pyproj import Transformer, Geod
from rasterio.transform import array_bounds
from .science import interpretation


def context_features(document):
    if not document:
        return []
    if document.get("crs"):
        raise ValueError(
            "Context layers must use WGS84 GeoJSON without a legacy CRS member."
        )
    features = (
        document.get("features", [])
        if document.get("type") == "FeatureCollection"
        else [document]
    )
    if len(features) > 2000:
        raise ValueError("Limit presentation context to 2,000 features.")
    from shapely.geometry import shape

    for feature in features:
        geometry = feature.get("geometry")
        if not geometry:
            raise ValueError("Context requires GeoJSON Features with geometry.")
        obj = shape(geometry)
        if not obj.is_valid or obj.is_empty:
            raise ValueError("Context contains invalid or empty geometry.")
        x0, y0, x1, y1 = obj.bounds
        if x0 < -180 or x1 > 180 or y0 < -90 or y1 > 90:
            raise ValueError("Context coordinates must be WGS84 longitude/latitude.")
    return features


def decorate_map(ax, scene):
    """True-north arrow and geodesic scale evaluated locally at the map center."""
    west, south, east, north = array_bounds(*scene.shape, scene.transform)
    to_geo = Transformer.from_crs(scene.crs, 4326, always_xy=True)
    to_map = Transformer.from_crs(4326, scene.crs, always_xy=True)
    geod = Geod(ellps="WGS84")
    cx, cy = (west + east) / 2, (south + north) / 2
    lon, lat = to_geo.transform(cx, cy)
    lon2, lat2, _ = geod.fwd(lon, lat, 0, 1000)
    nx, ny = to_map.transform(lon2, lat2)
    dx, dy = (nx - cx) / (east - west), (ny - cy) / (north - south)
    length = np.hypot(dx, dy)
    if length > 0 and np.isfinite(length):
        dx, dy = dx / length * 0.07, dy / length * 0.07
        ax.annotate(
            "N",
            xy=(0.91 + dx, 0.83 + dy),
            xytext=(0.91, 0.83),
            xycoords="axes fraction",
            ha="center",
            va="center",
            fontsize=10,
            weight="bold",
            arrowprops={"arrowstyle": "-|>", "color": "#183b45", "lw": 1.5},
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.85},
        )
    x0, y0 = west + 0.07 * (east - west), south + 0.07 * (north - south)
    l0, p0 = to_geo.transform(x0, y0)
    l1, p1 = to_geo.transform(x0 + 0.22 * (east - west), y0)
    _, _, meters = geod.inv(l0, p0, l1, p1)
    if not np.isfinite(meters) or meters <= 0:
        return
    magnitude = 10 ** np.floor(np.log10(meters))
    distance = max(
        v * magnitude for v in [0.1, 0.2, 0.5, 1, 2, 5] if v * magnitude <= meters
    )
    fraction = distance / meters * 0.22
    ax.plot(
        [0.07, 0.07 + fraction],
        [0.07, 0.07],
        transform=ax.transAxes,
        color="white",
        lw=7,
    )
    ax.plot(
        [0.07, 0.07 + fraction],
        [0.07, 0.07],
        transform=ax.transAxes,
        color="#15343d",
        lw=3,
    )
    label = f"{distance / 1000:g} km" if distance >= 1000 else f"{distance:g} m"
    ax.text(
        0.07,
        0.095,
        f"0                 {label}",
        transform=ax.transAxes,
        fontsize=8,
        bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "none", "pad": 2},
    )


def figure(result, metadata=None, context=None):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap, BoundaryNorm
    from matplotlib.patches import Patch, Rectangle
    from .detectors import REGISTRY

    metadata = metadata or result.report.get("presentation", {})
    fig = plt.figure(figsize=(11.69, 8.27), facecolor="#ffffff")
    fig.text(
        0.045,
        0.957,
        "GEOSENSE AI  /  ENVIRONMENTAL OBSERVATION",
        fontsize=9,
        color="#347678",
        weight="bold",
    )
    title = metadata.get("title") or REGISTRY[result.report["detector"]].title
    fig.text(
        0.045,
        0.902,
        textwrap.shorten(title, 86, placeholder="..."),
        fontsize=19 if len(title) < 70 else 16,
        color="#173c48",
        weight="bold",
    )
    subtitle = (
        metadata.get("study_area")
        or "Study area defined by the supplied raster / boundary"
    )
    fig.text(
        0.045,
        0.868,
        textwrap.shorten(subtitle, 110, placeholder="..."),
        fontsize=10,
        color="#52656c",
    )
    ax = fig.add_axes([0.075, 0.20, 0.59, 0.61])
    classes, labels, colors = interpretation(result)
    west, south, east, north = array_bounds(*result.scene.shape, result.scene.transform)
    ax.imshow(
        np.ma.masked_where(classes == 255, classes),
        extent=(west, east, south, north),
        cmap=ListedColormap(colors),
        norm=BoundaryNorm(np.arange(len(colors) + 1) - 0.5, len(colors)),
        interpolation="nearest",
    )
    ax.set_facecolor("#f6f7f8")
    ax.tick_params(labelsize=8)
    ax.ticklabel_format(style="plain", useOffset=False)
    ax.grid(color="#52656c", alpha=0.16, linewidth=0.5)
    ax.set_xlabel(
        "Longitude (degrees)"
        if result.scene.crs.is_geographic
        else "Easting (map units)",
        fontsize=8,
    )
    ax.set_ylabel(
        "Latitude (degrees)"
        if result.scene.crs.is_geographic
        else "Northing (map units)",
        fontsize=8,
    )
    if result.scene.crs.is_geographic:
        ax.set_aspect(1 / max(0.15, np.cos(np.radians((south + north) / 2))))
    from shapely.geometry import shape
    from shapely.ops import transform

    transformer = Transformer.from_crs(4326, result.scene.crs, always_xy=True)
    features = context_features(context)

    def draw(geom):
        if geom.geom_type.startswith("Multi") or geom.geom_type == "GeometryCollection":
            for part in geom.geoms:
                draw(part)
        elif geom.geom_type == "Polygon":
            ax.plot(*geom.exterior.xy, color="#294c60", lw=0.7)
            for ring in geom.interiors:
                ax.plot(*ring.xy, color="#294c60", lw=0.5)
        elif geom.geom_type == "LineString":
            ax.plot(*geom.xy, color="#456b8c", lw=0.7)
        elif geom.geom_type == "Point":
            ax.plot(geom.x, geom.y, "o", ms=3, color="#193b4a")

    for i, feature in enumerate(features):
        geom = transform(transformer.transform, shape(feature["geometry"]))
        draw(geom)
        label = feature.get("properties", {}).get("name")
        if label and i < 30:
            point = geom.representative_point()
            if west <= point.x <= east and south <= point.y <= north:
                ax.annotate(
                    str(label)[:45],
                    (point.x, point.y),
                    xytext=(3, 3),
                    textcoords="offset points",
                    fontsize=7,
                    clip_on=True,
                    bbox={
                        "facecolor": "white",
                        "edgecolor": "none",
                        "alpha": 0.7,
                        "pad": 1,
                    },
                )
    ax.set_xlim(west, east)
    ax.set_ylim(south, north)
    decorate_map(ax, result.scene)
    side = fig.add_axes([0.71, 0.20, 0.25, 0.62])
    side.axis("off")
    side.text(0, 1, "MAP KEY", fontsize=10, color="#173c48", weight="bold")
    handles = [
        Patch(facecolor=color, label=textwrap.shorten(label, 34, placeholder="..."))
        for color, label in zip(colors, labels)
    ]
    handles.append(
        Patch(
            facecolor="#f6f7f8", edgecolor="#aaa", label="No data / outside study area"
        )
    )
    if features:
        from matplotlib.lines import Line2D

        handles.append(
            Line2D(
                [0],
                [0],
                color="#294c60",
                marker="o",
                markersize=3,
                lw=0.7,
                label="Supplied context / named places",
            )
        )
    side.legend(
        handles=handles,
        loc="upper left",
        bbox_to_anchor=(-0.04, 0.97),
        frameon=False,
        fontsize=8,
        labelspacing=0.8,
    )
    reduced = bool(
        result.scene.processing and result.scene.processing.get("reduced_resolution")
    )
    y = 0.59
    summary = [
        (
            "SELECTED AREA" + (" (APPROX.)" if reduced else ""),
            f"{result.report['area_km2']:,.2f} km²",
        ),
        ("MAPPING METHOD", result.report["method"]),
        ("COORDINATE SYSTEM", str(result.scene.crs)),
        (
            "REFERENCE / CURRENT",
            f"{metadata.get('before_date') or 'Not supplied'} / {metadata.get('after_date') or 'Not supplied'}",
        ),
    ]
    for heading, value in summary:
        side.text(0, y, heading, fontsize=7, color="#63777d", weight="bold")
        side.text(
            0,
            y - 0.045,
            textwrap.fill(value, 36),
            fontsize=9,
            color="#173c48",
            va="top",
        )
        y -= 0.10
    # A global locator is schematic, without an unlicensed online basemap.
    locator = fig.add_axes([0.74, 0.18, 0.19, 0.085])
    locator.set_xlim(-180, 180)
    locator.set_ylim(-90, 90)
    locator.set_xticks([-180, 0, 180])
    locator.set_yticks([-90, 0, 90])
    locator.tick_params(labelsize=5)
    locator.grid(alpha=0.2)
    locator.set_title("Global extent locator (no basemap)", fontsize=7)
    transformer = Transformer.from_crs(result.scene.crs, 4326, always_xy=True)
    x0, y0 = transformer.transform(west, south)
    x1, y1 = transformer.transform(east, north)
    locator.add_patch(
        Rectangle(
            (min(x0, x1), min(y0, y1)),
            max(abs(x1 - x0), 1),
            max(abs(y1 - y0), 1),
            facecolor="#c8413c",
            alpha=0.65,
        )
    )
    source = (
        metadata.get("source") or "Source not supplied - complete before publication"
    )
    author = metadata.get("author") or "Author not supplied"
    fig.text(
        0.045,
        0.115,
        textwrap.shorten(
            f"Source: {source} | Prepared by: {author}", 150, placeholder="..."
        ),
        fontsize=8,
        color="#455e65",
    )
    status = (
        "SYNTHETIC DEMONSTRATION"
        if result.report["synthetic"]
        else "UNVALIDATED SCREENING / USER-SUPPLIED CLASSIFICATION"
    )
    if result.report.get("validation"):
        status = "REFERENCE COMPARISON AVAILABLE - SEE METHODS REPORT"
    fig.text(
        0.045,
        0.078,
        status + ("  |  REDUCED RESOLUTION" if reduced else ""),
        fontsize=8,
        weight="bold",
        color="#a14032",
    )
    fig.text(
        0.045,
        0.045,
        "Scale and north evaluated locally. Extent-wide scale varies. Severity is not fire intensity; see methods and limitations.",
        fontsize=7,
        color="#52656c",
    )
    return fig


def map_bytes(result, extension="png", metadata=None, context=None):
    import matplotlib.pyplot as plt

    fig = figure(result, metadata, context)
    buffer = BytesIO()
    fig.savefig(buffer, format=extension, dpi=220)
    plt.close(fig)
    return buffer.getvalue()
