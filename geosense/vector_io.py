"""Bounded vector package readers. Archives are inspected in memory, never extracted."""

from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import ZipFile
import json
import hashlib
from fiona.io import ZipMemoryFile
from pyproj import CRS, Transformer
from shapely.geometry import shape, mapping, MultiPolygon, MultiLineString, MultiPoint
from shapely.ops import transform
from defusedxml import ElementTree as ET

MAX_BYTES = 750_000_000
MAX_FEATURES = 100_000


@dataclass
class Package:
    files: dict
    layers: list
    inventory: list
    sha256: str


def archive_files(payload):
    with ZipFile(BytesIO(payload)) as archive:
        items = [i for i in archive.infolist() if not i.is_dir()]
        if len(items) > 3000 or sum(i.file_size for i in items) > MAX_BYTES:
            raise ValueError("Package exceeds 3,000 files or 750 MB uncompressed.")
        result = {}
        for item in items:
            path = PurePosixPath(item.filename.replace("\\", "/"))
            if path.is_absolute() or ".." in path.parts or ":" in str(path):
                raise ValueError("Archive contains an unsafe path.")
            if item.flag_bits & 1:
                raise ValueError("Encrypted archives are not supported.")
            name = str(path)
            if name.lower() in {n.lower() for n in result}:
                raise ValueError("Archive contains duplicate filenames.")
            result[name] = archive.read(item)
        return result


def load_package(uploads):
    files = {}
    seen = set()
    digest = hashlib.sha256()
    for name, payload in uploads:
        digest.update(name.encode())
        digest.update(payload)
        members = (
            archive_files(payload) if name.lower().endswith(".zip") else {name: payload}
        )
        for member, data in members.items():
            path = PurePosixPath(member.replace("\\", "/"))
            if (
                path.is_absolute()
                or ".." in path.parts
                or ":" in str(path)
                or not path.name
            ):
                raise ValueError("Upload contains an unsafe path.")
            member = str(path)
            if member.casefold() in seen:
                raise ValueError(
                    f"Duplicate upload: {member}. Upload either the ZIP or its files."
                )
            seen.add(member.casefold())
            files[member] = data
    if len(files) > 3000 or sum(map(len, files.values())) > MAX_BYTES:
        raise ValueError("Combined input exceeds 750 MB uncompressed.")
    groups = {}
    inventory = []
    for name, data in files.items():
        path = PurePosixPath(name)
        suffix = path.suffix.lower()
        groups.setdefault(str(path.with_suffix("")), {})[suffix] = name
        role = {
            ".shp": "Geometry",
            ".shx": "Shapefile index",
            ".dbf": "Attributes",
            ".prj": "Coordinate system",
            ".cpg": "Text encoding",
            ".sld": "Style reference (not applied)",
            ".xml": "Metadata reference",
            ".xlsx": "Summary spreadsheet (not analysed)",
            ".xls": "Summary spreadsheet (not analysed)",
            ".osc": "OSM change file (not applied)",
            ".json": "Vector / JSON",
            ".geojson": "Vector",
            ".kml": "Vector",
            ".kmz": "Vector archive",
        }.get(suffix, "Companion / unsupported")
        inventory.append({"file": name, "role": role, "bytes": len(data)})
    layers = []
    for stem, variants in sorted(groups.items()):
        formats = [
            ext
            for ext in [".geojson", ".json", ".shp", ".kml", ".kmz"]
            if ext in variants
        ]
        # Arbitrary JSON documents are metadata, not spatial layers.
        for ext in [".geojson", ".json"]:
            if ext in formats:
                try:
                    doc = json.loads(files[variants[ext]])
                    if not isinstance(doc, dict) or doc.get("type") not in [
                        "FeatureCollection",
                        "Feature",
                    ]:
                        formats.remove(ext)
                except (ValueError, UnicodeError):
                    formats.remove(ext)
        if formats:
            layers.append(
                {
                    "name": stem,
                    "formats": formats,
                    "files": variants,
                    "suggested_role": "event"
                    if "observedevent" in stem.lower()
                    else "aoi"
                    if "areaofinterest" in stem.lower()
                    else "context",
                }
            )
    return Package(files, layers, inventory, digest.hexdigest())


def kml_document(payload):
    root = ET.fromstring(payload)

    def local(element):
        return element.tag.split("}")[-1]

    def child(element, name):
        return next((x for x in element.iter() if local(x) == name), None)

    def coordinates(element):
        node = child(element, "coordinates")
        if node is None or not node.text:
            raise ValueError("KML geometry is missing coordinates.")
        return [list(map(float, value.split(",")[:2])) for value in node.text.split()]

    def geometry(element):
        kind = local(element)
        if kind == "Point":
            return {"type": "Point", "coordinates": coordinates(element)[0]}
        if kind == "LineString":
            return {"type": "LineString", "coordinates": coordinates(element)}
        if kind == "Polygon":
            outer = child(element, "outerBoundaryIs")
            if outer is None:
                raise ValueError("KML polygon has no outer ring.")
            return {
                "type": "Polygon",
                "coordinates": [coordinates(outer)]
                + [coordinates(x) for x in element if local(x) == "innerBoundaryIs"],
            }
        if kind == "MultiGeometry":
            return {
                "type": "GeometryCollection",
                "geometries": [
                    geometry(x)
                    for x in element
                    if local(x) in {"Point", "LineString", "Polygon", "MultiGeometry"}
                ],
            }
        raise ValueError(f"Unsupported KML geometry: {kind}")

    features = []
    for placemark in root.iter():
        if local(placemark) != "Placemark":
            continue
        geom = next(
            (
                x
                for x in placemark
                if local(x) in {"Point", "LineString", "Polygon", "MultiGeometry"}
            ),
            None,
        )
        if geom is None:
            continue
        properties = {}
        for name in ["name", "description"]:
            value = child(placemark, name)
            if value is not None:
                properties[name] = value.text or ""
        for node in placemark.iter():
            if local(node) == "SimpleData":
                properties[node.get("name", "field")] = node.text
            if local(node) == "Data":
                value = child(node, "value")
                properties[node.get("name", "field")] = (
                    value.text if value is not None else None
                )
        features.append(
            {"type": "Feature", "properties": properties, "geometry": geometry(geom)}
        )
    return {"type": "FeatureCollection", "features": features}


def read_layer(package, layer_name, selected_format=None, assumed_crs=None):
    layer = next(x for x in package.layers if x["name"] == layer_name)
    ext = selected_format or layer["formats"][0]
    filename = layer["files"][ext]
    data = package.files[filename]
    source_crs = "EPSG:4326"
    if ext in [".json", ".geojson"]:
        doc = json.loads(data)
        crs = doc.get("crs")
        if crs:
            source_crs = crs.get("properties", {}).get("name")
            if not source_crs:
                raise ValueError("Unrecognized GeoJSON CRS metadata.")
    elif ext == ".shp":
        required = [".shp", ".shx", ".dbf"]
        missing = [s for s in required if s not in layer["files"]]
        if missing:
            raise ValueError("Missing Shapefile companions: " + ", ".join(missing))
        bundle = BytesIO()
        with ZipFile(bundle, "w") as archive:
            for suffix in required + [".prj", ".cpg"]:
                if suffix in layer["files"]:
                    archive.writestr(
                        "layer" + suffix, package.files[layer["files"][suffix]]
                    )
        with (
            ZipMemoryFile(bundle.getvalue()) as memory,
            memory.open("layer.shp") as source,
        ):
            source_crs = source.crs_wkt or assumed_crs
            if not source_crs:
                raise ValueError(
                    "Shapefile CRS is missing. Include its .prj or explicitly supply the correct EPSG code."
                )
            from fiona.model import to_dict

            if len(source) > MAX_FEATURES:
                raise ValueError("Layer exceeds 100,000 features; subset it first.")
            doc = {
                "type": "FeatureCollection",
                "features": [to_dict(f) for f in source],
            }
    else:
        if ext == ".kmz":
            members = archive_files(data)
            candidates = [n for n in members if n.lower().endswith(".kml")]
            if len(candidates) != 1:
                raise ValueError(
                    "KMZ must contain exactly one KML document. Upload individual KMLs for multi-document archives."
                )
            data = members[candidates[0]]
        doc = kml_document(data)
    features = doc.get("features", []) if doc["type"] == "FeatureCollection" else [doc]
    if len(features) > MAX_FEATURES:
        raise ValueError("Layer exceeds 100,000 features; subset it first.")
    transformer = Transformer.from_crs(
        CRS.from_user_input(source_crs), 4326, always_xy=True
    )
    result, invalid, empty = [], 0, 0
    for feature in features:
        if not feature.get("geometry"):
            empty += 1
            continue
        geometry = transform(transformer.transform, shape(feature["geometry"]))
        if geometry.geom_type == "GeometryCollection" and len(geometry.geoms):
            parts = list(geometry.geoms)
            if all(g.geom_type == "Polygon" for g in parts):
                geometry = MultiPolygon(parts)
            elif all(g.geom_type == "LineString" for g in parts):
                geometry = MultiLineString(parts)
            elif all(g.geom_type == "Point" for g in parts):
                geometry = MultiPoint(parts)
        if geometry.is_empty:
            empty += 1
            continue
        if not geometry.is_valid:
            invalid += 1
            continue
        x0, y0, x1, y1 = geometry.bounds
        if not (-180 <= x0 <= x1 <= 180 and -90 <= y0 <= y1 <= 90):
            raise ValueError(
                "Coordinates fall outside WGS84 after conversion; verify the source CRS."
            )
        result.append(
            {
                "type": "Feature",
                "properties": feature.get("properties") or {},
                "geometry": mapping(geometry),
            }
        )
    return {"type": "FeatureCollection", "features": result}, {
        "file": filename,
        "source_crs": str(source_crs),
        "features": len(result),
        "invalid_skipped": invalid,
        "empty_skipped": empty,
        "format": ext,
        "sha256": hashlib.sha256(package.files[filename]).hexdigest(),
    }
