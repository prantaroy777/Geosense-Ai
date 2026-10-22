"""Self-contained vector import workspace, independent of spectral detector controls."""

from io import BytesIO
from zipfile import ZipFile
import hashlib
import json
import streamlit as st
from .vector_io import load_package, read_layer
from .vector_analysis import vector_result, context_summary
from .pipeline import export_bundle, map_bytes
from .quality import vector_quality
from .run_store import save_run


@st.cache_data(max_entries=2, show_spinner=False)
def package_cached(files):
    return load_package(files)


@st.cache_data(max_entries=8, show_spinner=False)
def layer_cached(files, name, fmt, crs):
    return read_layer(load_package(files), name, fmt, crs or None)


def workspace():
    st.subheader("GIS package workspace")
    st.write(
        "Upload the original ZIP, or select the downloaded vector files together. Choose event polygons, a study boundary and context layers. No satellite TIFF is required."
    )
    uploads = st.file_uploader(
        "GIS package or component files",
        accept_multiple_files=True,
        type=[
            "zip",
            "shp",
            "shx",
            "dbf",
            "prj",
            "cpg",
            "json",
            "geojson",
            "kml",
            "kmz",
            "sld",
            "xml",
            "xlsx",
            "xls",
            "osc",
        ],
        key="vector_files",
    )
    if not uploads:
        st.info(
            "Recommended: upload the original Copernicus vector ZIP. For Shapefiles, include matching .shp + .shx + .dbf + .prj files."
        )
        return
    files = [(f.name, f.getvalue()) for f in uploads]
    try:
        with st.spinner("Inspecting package layers…"):
            package = package_cached(files)
        st.caption(
            "Equivalent formats with the same filename stem are grouped. Only your chosen representation is analysed."
        )
        with st.expander("Package inventory", expanded=False):
            st.dataframe(package.inventory, hide_index=True)
            st.warning(
                "SLD styles, XML metadata, Excel summaries and OSM change files are inventoried but not executed or used as analytical geometry. KML network links are not fetched."
            )
        if not package.layers:
            st.warning(
                "No readable vector layers found. Include geometry, not just DBF/SLD/metadata files."
            )
            return
        names = [entry["name"] for entry in package.layers]
        preferred = next(
            (
                i
                for i, entry in enumerate(package.layers)
                if entry["suggested_role"] == "event"
            ),
            0,
        )
        event_name = st.selectbox("Event polygon layer", names, index=preferred)
        layer = next(entry for entry in package.layers if entry["name"] == event_name)
        fmt = st.selectbox("Read event geometry from", layer["formats"])
        assumed = st.text_input(
            "Missing Shapefile CRS only: EPSG code",
            placeholder="Leave blank when .prj exists",
        )
        event, evidence = layer_cached(files, event_name, fmt, assumed)
        st.write(
            f"{len(event['features']):,} event features · source CRS: {evidence['source_crs']}"
        )
        if evidence["invalid_skipped"] or evidence["empty_skipped"]:
            st.warning(
                f"Excluded {evidence['invalid_skipped']} invalid and {evidence['empty_skipped']} empty geometries; repair the source if these are needed."
            )
        fields = sorted({k for f in event["features"] for k in f["properties"]})
        st.dataframe(
            [f["properties"] for f in event["features"][:100]], hide_index=True
        )
        class_field = st.selectbox(
            "Optional supplied class / damage field",
            [None] + fields,
            format_func=lambda x: x or "Single event class",
        )
        values = (
            sorted(
                {
                    str(f["properties"].get(class_field, "Unspecified"))
                    for f in event["features"]
                }
            )
            if class_field
            else []
        )
        selected = (
            st.multiselect("Classes to include", values, default=values)
            if class_field
            else None
        )
        options = [None] + [n for n in names if n != event_name]
        preferred_aoi = next(
            (
                entry["name"]
                for entry in package.layers
                if entry["suggested_role"] == "aoi"
            ),
            None,
        )
        aoi_name = st.selectbox(
            "Study-area boundary (clip event)",
            options,
            index=options.index(preferred_aoi) if preferred_aoi in options else 0,
            format_func=lambda x: x or "Use event extent",
        )
        context_names = st.multiselect(
            "Context layers: water, roads, places, land use",
            [n for n in names if n not in [event_name, aoi_name]],
        )
        title = st.text_input("Map title", value="Imported event extent")
        author = st.text_input("Prepared by")
        source = st.text_input(
            "Source / attribution",
            value="User-supplied vector product; verify producer attribution",
        )
        quality = vector_quality(
            event,
            evidence,
            source
            if source != "User-supplied vector product; verify producer attribution"
            else "",
        )
        with st.expander("Data-quality findings", expanded=False):
            st.dataframe(quality["findings"], hide_index=True)
            st.caption("Technical checks do not establish scientific accuracy.")
        fingerprint = hashlib.sha256(
            json.dumps(
                [
                    package.sha256,
                    event_name,
                    fmt,
                    assumed,
                    class_field,
                    selected,
                    aoi_name,
                    context_names,
                    title,
                    author,
                    source,
                ]
            ).encode()
        ).hexdigest()
        if st.session_state.get("vector_signature") != fingerprint:
            st.session_state.pop("vector_output", None)
            st.session_state["vector_signature"] = fingerprint
        if st.button("Build vector map and statistics", type="primary"):
            with st.spinner(
                "Clipping polygons, measuring geodesic areas and preparing the report…"
            ):
                aoi, aoi_info = (
                    layer_cached(files, aoi_name, None, assumed)
                    if aoi_name
                    else (None, None)
                )
                result = vector_result(event, event_name, aoi, class_field, selected)
                all_context, layers_export, summaries, warnings = [], {}, [], []
                if aoi:
                    all_context.extend(aoi["features"])
                    layers_export[aoi_name] = aoi
                for name in context_names:
                    doc, info = layer_cached(files, name, None, assumed)
                    layers_export[name] = doc
                    summaries.append(
                        {"layer": name, **context_summary(doc, result.features), **info}
                    )
                    all_context.extend(doc["features"])
                # Limit presentation complexity only; retain complete selected layers in the ZIP.
                from shapely.geometry import shape
                from shapely.ops import unary_union

                extent = unary_union(
                    [shape(f["geometry"]) for f in (aoi or result.features)["features"]]
                ).envelope
                visible = [
                    f for f in all_context if shape(f["geometry"]).intersects(extent)
                ]
                if len(visible) > 2000:
                    warnings.append(
                        f"Map shows the first 2,000 of {len(visible):,} intersecting context features. All selected context features are retained in the ZIP."
                    )
                context = {"type": "FeatureCollection", "features": visible[:2000]}
                result.report["inputs"] = {
                    "event": evidence,
                    "aoi": aoi_info,
                    "package_sha256": package.sha256,
                }
                result.report["context_intersections"] = summaries
                result.report["presentation_warnings"] = warnings
                result.report["package_inventory"] = package.inventory
                result.report["quality"] = quality
                metadata = {
                    "title": title,
                    "author": author,
                    "source": source,
                    "notes": "Imported vector product. Confirm class meanings with its producer.",
                }
                bundle = export_bundle(result, metadata, context)
                output = BytesIO()
                with (
                    ZipFile(BytesIO(bundle)) as original,
                    ZipFile(output, "w") as target,
                ):
                    for name in original.namelist():
                        target.writestr(name, original.read(name))
                    target.writestr("imported_event.geojson", json.dumps(event))
                    for i, (name, doc) in enumerate(layers_export.items()):
                        target.writestr(
                            f"layers/{i}_{name.split('/')[-1]}.geojson", json.dumps(doc)
                        )
                st.session_state["vector_output"] = (result, context, output.getvalue())
        if "vector_output" in st.session_state:
            result, context, bundle = st.session_state["vector_output"]
            st.metric(
                "Event area from polygon union", f"{result.report['area_km2']:,.3f} km²"
            )
            for warning in result.report["presentation_warnings"]:
                st.warning(warning)
            st.image(map_bytes(result, context=context))
            st.dataframe(result.report["class_statistics"], hide_index=True)
            st.caption(
                "Areas use source polygons, not display pixels. Overlaps between different classes can make class totals exceed the overall union area."
            )
            if result.report["context_intersections"]:
                st.dataframe(result.report["context_intersections"], hide_index=True)
                st.caption(
                    "Intersection counts indicate possible exposure, not verified damage."
                )
            st.download_button(
                "Download vector maps, layers and report",
                bundle,
                "geosense_vector_results.zip",
                "application/zip",
            )
            if st.button("Save this run to local library", key="save_vector"):
                saved = save_run(bundle, title)
                st.success(
                    f"Saved run {saved['run_id'][:12]}. Open Monitoring & run library to review it later."
                )
            with ZipFile(BytesIO(bundle)) as archive:
                st.download_button(
                    "Download vector research report",
                    archive.read("research_report.pdf"),
                    "vector_report.pdf",
                    "application/pdf",
                )
    except Exception as error:
        st.session_state.pop("vector_output", None)
        st.error(f"Package could not be processed: {error}")
