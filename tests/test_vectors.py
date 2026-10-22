import json
from io import BytesIO
from zipfile import ZipFile
import pytest
from shapely.geometry import box, mapping
from geosense.vector_io import load_package, read_layer
from geosense.vector_analysis import vector_result, geodesic_area


def document():
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"damage": "Affected"},
                "geometry": mapping(box(13, 52, 13.01, 52.01)),
            }
        ],
    }


def test_geojson_legacy_crs_and_grouping():
    doc = document()
    doc["crs"] = {
        "type": "name",
        "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
    }
    package = load_package(
        [
            ("event.json", json.dumps(doc).encode()),
            ("event.shp", b"unused"),
            ("event.sld", b"style"),
        ]
    )
    assert len(package.layers) == 1
    result, info = read_layer(package, "event")
    assert len(result["features"]) == 1
    assert "crs" not in result
    assert info["format"] == ".json"


def test_zip_traversal_rejected():
    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr("../bad.json", "{}")
    with pytest.raises(ValueError, match="unsafe"):
        load_package([("bad.zip", stream.getvalue())])


def test_shapefile_missing_companions():
    package = load_package([("event.shp", b"unused")])
    with pytest.raises(ValueError, match="companions"):
        read_layer(package, "event")


def test_kml_polygon_holes_and_properties():
    kml = b"""<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark><name>Area</name><ExtendedData><Data name="grade"><value>High</value></Data></ExtendedData><Polygon><outerBoundaryIs><LinearRing><coordinates>13,52 14,52 14,53 13,53 13,52</coordinates></LinearRing></outerBoundaryIs><innerBoundaryIs><LinearRing><coordinates>13.2,52.2 13.2,52.3 13.3,52.3 13.3,52.2 13.2,52.2</coordinates></LinearRing></innerBoundaryIs></Polygon></Placemark></Document></kml>"""
    package = load_package([("area.kml", kml)])
    doc, _ = read_layer(package, "area")
    assert doc["features"][0]["properties"]["grade"] == "High"
    assert len(doc["features"][0]["geometry"]["coordinates"]) == 2


def test_vector_union_does_not_double_count():
    doc = document()
    doc["features"] *= 2
    result = vector_result(doc, "event", class_field="damage")
    assert result.report["area_km2"] == pytest.approx(
        geodesic_area(box(13, 52, 13.01, 52.01)) / 1e6
    )
    assert result.features["features"][0]["properties"]["damage"] == "Affected"
    assert result.report["vector_product"]


def test_points_are_not_event_areas():
    doc = document()
    doc["features"][0]["geometry"] = {"type": "Point", "coordinates": [13, 52]}
    with pytest.raises(ValueError, match="Polygon"):
        vector_result(doc, "event")


def test_projected_geojson_is_reprojected():
    from pyproj import Transformer
    from shapely.ops import transform

    doc = document()
    geom = transform(
        Transformer.from_crs(4326, 3857, always_xy=True).transform,
        box(13, 52, 13.01, 52.01),
    )
    doc["features"][0]["geometry"] = mapping(geom)
    doc["crs"] = {"type": "name", "properties": {"name": "EPSG:3857"}}
    package = load_package([("projected.json", json.dumps(doc).encode())])
    output, _ = read_layer(package, "projected")
    from shapely.geometry import shape

    assert shape(output["features"][0]["geometry"]).bounds == pytest.approx(
        (13, 52, 13.01, 52.01)
    )


def test_vector_aoi_clip_and_filter():
    doc = document()
    aoi = document()
    aoi["features"][0]["geometry"] = mapping(box(13, 52, 13.005, 52.01))
    result = vector_result(doc, "event", aoi, "damage", ["Affected"])
    assert result.report["area_km2"] == pytest.approx(
        geodesic_area(box(13, 52, 13.005, 52.01)) / 1e6
    )
    with pytest.raises(ValueError, match="No event"):
        vector_result(doc, "event", class_field="damage", selected_values=[])
