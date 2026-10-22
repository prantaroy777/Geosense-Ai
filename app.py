"""Run with: python -m streamlit run app.py"""

from geosense import __version__
import hashlib
import json
from pathlib import Path
import streamlit as st
from geosense.demo import demo_scenes, scene_bytes
from geosense.detectors import REGISTRY
from geosense.pipeline import analyze, export_bundle, map_bytes
from geosense.raster import inspect_raster, read_scene
from geosense.science import compare_reference
from geosense.cartography import context_features
from io import BytesIO
from zipfile import ZipFile

st.set_page_config(page_title="GeoSense AI", page_icon="🌍", layout="wide")
st.title("GeoSense AI")
st.caption(
    "Understand your imagery. Review the evidence. Create a presentation-ready map."
)
st.markdown(
    "**1 · Choose data and analysis** → **2 · Review inputs** → **3 · Map and validate** → **4 · Export**"
)

with st.sidebar:
    st.header("Analysis workspace")
    mode = st.radio(
        "Data source",
        [
            "Synthetic demo",
            "Upload GeoTIFF",
            "GIS vector package",
            "Monitoring & run library",
        ],
    )
    if mode == "GIS vector package":
        st.caption(
            "Import provider event polygons and supporting GIS layers. Spectral detection controls are not needed."
        )
if mode == "Monitoring & run library":
    from geosense.monitoring_ui import workspace

    workspace()
    st.stop()
if mode == "GIS vector package":
    from geosense.vector_ui import workspace

    workspace()
    st.stop()
with st.sidebar:
    detector_id = st.selectbox(
        "Analysis",
        list(REGISTRY),
        format_func=lambda k: REGISTRY[k].title,
        key="analysis_choice",
    )
    detector = REGISTRY[detector_id]
    threshold = st.number_input(
        "Selected class value"
        if detector_id == "prepared_mask"
        else "Detection threshold",
        value=detector.threshold,
        key=f"threshold_{detector_id}",
    )
    budget = st.selectbox(
        "Processing pixel budget", [250_000, 1_000_000, 4_000_000, 16_000_000], index=1
    )
    st.caption(
        "Large scenes are sampled to this budget. Crop a small area for native-resolution results."
    )
    min_pixels = st.number_input(
        "Minimum connected patch (processed pixels)",
        min_value=1,
        value=1 if detector_id == "prepared_mask" else 9,
        step=1,
        key=f"patch_{detector_id}",
    )
    aoi_file = st.file_uploader(
        "Optional study boundary (WGS84 GeoJSON)", type=["geojson", "json"]
    )
    st.caption("Forest and crop screening should use a matching land-cover boundary.")

st.info(detector.description)
if detector_id == "burned_area":
    st.caption(
        "Severity legend: unburned/regrowth < 0.10; low 0.10–0.27; moderate-low 0.27–0.44; moderate-high 0.44–0.66; high ≥ 0.66 dNBR. These reference classes require local validation and do not measure fire intensity."
    )
with st.expander(
    "Presentation settings · title, credits, dates and context", expanded=False
):
    title = st.text_input(
        "Map title",
        max_chars=100,
        placeholder="e.g. Post-fire vegetation effects — study area",
    )
    study_area = st.text_input("Study area name", max_chars=120)
    c1, c2 = st.columns(2)
    with c1:
        author = st.text_input("Prepared by", max_chars=100)
        before_date = st.text_input(
            "Reference acquisition date / period",
            max_chars=60,
            placeholder="YYYY-MM-DD or date range",
        )
    with c2:
        institution = st.text_input("Institution", max_chars=100)
        after_date = st.text_input(
            "Current acquisition date / period",
            max_chars=60,
            placeholder="YYYY-MM-DD or date range",
        )
    source = st.text_input(
        "Data source and attribution",
        max_chars=240,
        placeholder="Provider, product, collection, licence and/or DOI",
    )
    notes = st.text_area("Methods / field observations", max_chars=1500)
    context_upload = st.file_uploader(
        "Optional map context: boundaries, rivers, roads or places (WGS84 GeoJSON)",
        type=["geojson", "json"],
        key="context",
    )
    st.caption(
        "Features may have a 'name' property for labels. Up to 2,000 features; first 30 named features are labelled. No online basemap or invented place names are added."
    )
metadata = {
    "title": title,
    "study_area": study_area,
    "author": author,
    "institution": institution,
    "before_date": before_date,
    "after_date": after_date,
    "source": source,
    "notes": notes,
}
with st.expander("Optional accuracy check · independent reference mask"):
    reference_upload = st.file_uploader(
        "Reference GeoTIFF (single-band labels)", type=["tif", "tiff"], key="reference"
    )
    reference_class = st.number_input("Reference positive class", value=1.0)
    st.caption(
        "Use independent labels, not the same input mask. Metrics measure pixel agreement on the processed grid; they are not a guarantee of accuracy elsewhere."
    )
before = after = None
provenance = {}
# Streamlit hashes the wrapper, but does not track changes in its helper modules.
# Include their contents so an updated reader cannot reuse an older result schema.
PROCESSING_REVISION = hashlib.sha256(
    b"".join(
        path.read_bytes()
        for path in sorted((Path(__file__).parent / "geosense").glob("*.py"))
    )
).hexdigest()


@st.cache_data(show_spinner=False, max_entries=4)
def inspect_cached(payload, revision):
    return inspect_raster(payload)


@st.cache_data(show_spinner=False, max_entries=2)
def read_cached(payload, mapping, name, scale, offset, scl, budget, bounds, revision):
    return read_scene(
        payload, mapping, name, scale, offset, scl, max_pixels=budget, bounds=bounds
    )


def choose_mask():
    st.session_state["analysis_choice"] = "prepared_mask"


def upload_scene(label, key):
    upload = st.file_uploader(label, type=["tif", "tiff"], key=key)
    if upload is None:
        return None
    payload = upload.getvalue()
    info = inspect_cached(payload, PROCESSING_REVISION)
    st.json(info, expanded=False)
    st.write(f"{info['width']:,} × {info['height']:,} pixels · {info['bands']} band(s)")
    if (
        info["bands"] == 1
        and info.get("binary_sample", False)
        and detector_id != "prepared_mask"
    ):
        st.warning(
            "The sample contains only 0 and 1. This appears to be an existing event mask, not a thermal or multispectral scene. Check its provider's class definitions."
        )
        st.button(
            "Use existing event mask workflow",
            on_click=choose_mask,
            key=f"{key}_switch",
        )
        return None
    if info["bands"] < len(detector.bands):
        st.warning(
            f"This analysis needs {len(detector.bands)} distinct bands. Choose Existing event mask for a classified raster, or supply the required spectral bands."
        )
        return None
    bounds = None
    if st.checkbox("Crop before processing", key=f"{key}_crop"):
        st.caption(
            f"Bounding box coordinates in {info['crs']}. The crop is read before resizing or analysis."
        )
        bounds = [
            st.number_input(
                axis, value=float(value), format="%.6f", key=f"{key}_{axis}"
            )
            for axis, value in zip(["West", "South", "East", "North"], info["bounds"])
        ]
    st.caption(
        "Map bands explicitly. Band order alone does not identify a sensor or wavelength."
    )
    mapping = {}
    descriptions = [str(d).lower() if d else "" for d in info["descriptions"]]
    for role in detector.bands:
        suggested = (
            descriptions.index(role) + 1
            if role in descriptions
            else (1 if role == "mask" and info["bands"] == 1 else 0)
        )
        index = st.selectbox(
            f"{role} band",
            list(range(info["bands"] + 1)),
            index=suggested,
            format_func=lambda i: "Choose a band" if i == 0 else f"Band {i}",
            key=f"{key}_{role}",
        )
        if index:
            mapping[role] = index
    if detector_id == "prepared_mask":
        scale, offset = 1.0, 0.0
        st.caption(
            "Class raster: select the class value in the sidebar. Cloud-classification bands and spectral calibration controls are not required."
        )
    else:
        scale = st.number_input(
            "Additional scale", value=1.0, format="%.6f", key=f"{key}_scale"
        )
        offset = st.number_input(
            "Additional offset", value=0.0, format="%.6f", key=f"{key}_offset"
        )
        st.caption(
            "Dataset scale/offset metadata is applied first. Use surface reflectance for optical analyses and Kelvin for thermal analysis."
        )
    scl = (
        0
        if detector_id == "prepared_mask"
        else st.selectbox(
            "Optional Sentinel-2 SCL band",
            [0] + [i for i in range(1, info["bands"] + 1) if i not in mapping.values()],
            format_func=lambda i: "None" if i == 0 else f"Band {i}",
            key=f"{key}_scl",
        )
    )
    if not scl and detector_id != "prepared_mask":
        st.warning(
            "No cloud classifier selected. Supply cloud-masked imagery or embed a Sentinel-2 SCL band; clouds can create false detections."
        )
    provenance[key] = {
        "filename": upload.name,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "band_mapping": mapping,
        "additional_scale": scale,
        "additional_offset": offset,
        "scl_band": scl or None,
        "pixel_budget": budget,
        "crop_bounds": bounds,
    }
    if len(mapping) != len(detector.bands):
        return None
    scene = read_cached(
        payload,
        mapping,
        upload.name,
        scale,
        offset,
        scl or None,
        budget,
        bounds,
        PROCESSING_REVISION,
    )
    if scene.processing["reduced_resolution"]:
        st.warning(
            f"Reduced-resolution analysis: {scene.shape[1]:,} × {scene.shape[0]:,} pixels. Nearest-neighbor sampling may miss small patches; exported areas are approximate. Crop a smaller region for native detail."
        )
    return scene


try:
    context = json.loads(context_upload.getvalue()) if context_upload else None
    context_features(context)
    if mode == "Synthetic demo":
        st.warning(
            "SYNTHETIC DEMO — generated reflectance and temperature patterns, not a real satellite event."
        )
        before, after = demo_scenes()
        with st.expander("Download sample inputs to try the upload workflow"):
            st.write(
                "Bands: 1 red, 2 green, 3 NIR, 4 SWIR1, 5 SWIR2, 6 thermal (Kelvin), 7 event mask."
            )
            st.download_button(
                "Before GeoTIFF", scene_bytes(before), "synthetic_before.tif"
            )
            st.download_button(
                "After GeoTIFF", scene_bytes(after), "synthetic_after.tif"
            )
    else:
        columns = st.columns(2 if detector.needs_before else 1)
        with columns[0]:
            st.subheader("After / current scene")
            after = upload_scene("Current GeoTIFF", "after")
        if detector.needs_before:
            with columns[1]:
                st.subheader("Before / reference scene")
                before = upload_scene("Baseline GeoTIFF", "before")
        st.caption(
            "Use preprocessed, georeferenced band stacks. Different baseline grids are aligned automatically. Raw SAFE/JP2 and SAR products are not yet supported."
        )
    aoi = json.loads(aoi_file.getvalue()) if aoi_file else None
    # Changing inputs clears old outputs so results cannot be mistaken for a new run.
    signature = hashlib.sha256(
        json.dumps(
            [
                mode,
                detector_id,
                threshold,
                min_pixels,
                aoi,
                provenance,
                metadata,
                context,
                hashlib.sha256(reference_upload.getvalue()).hexdigest()
                if reference_upload
                else None,
                reference_class,
            ],
            sort_keys=True,
        ).encode()
    ).hexdigest()
    if st.session_state.get("input_signature") != signature:
        st.session_state.pop("result", None)
        st.session_state.pop("bundle", None)
        st.session_state["input_signature"] = signature
    if st.button(
        "Run analysis",
        type="primary",
        disabled=after is None or (detector.needs_before and before is None),
    ):
        with st.spinner("Calculating indices, extracting polygons and creating maps…"):
            result = analyze(
                after, detector_id, before, threshold, aoi, int(min_pixels)
            )
            result.report["inputs"] = provenance
            if reference_upload:
                reference = read_scene(
                    reference_upload.getvalue(),
                    {"mask": 1},
                    reference_upload.name,
                    max_pixels=budget,
                )
                result.report["validation"] = compare_reference(
                    result, reference, reference_class
                )
                result.report["validation"]["sha256"] = hashlib.sha256(
                    reference_upload.getvalue()
                ).hexdigest()
                result.report["validation"]["processing"] = reference.processing
            st.session_state["bundle"] = export_bundle(result, metadata, context)
            st.session_state["result"] = result
    if "result" in st.session_state:
        result = st.session_state["result"]
        area, patches, coverage = st.columns(3)
        reduced = result.scene.processing and result.scene.processing.get(
            "reduced_resolution"
        )
        area.metric(
            "Approximate sampled area" if reduced else "Candidate area",
            f"{result.report['area_km2']:.3f} km²",
        )
        patches.metric("Polygons", result.report["polygon_count"])
        coverage.metric(
            "Candidate fraction of valid pixels",
            f"{result.report['detected_fraction_of_valid']:.1%}",
        )
        st.image(
            map_bytes(result, context=context),
            caption="A4 landscape layout · classified map, local north and scale, coordinates, legend and attribution.",
        )
        with st.expander("Class distribution and interpretation", expanded=True):
            st.dataframe(
                result.report["class_statistics"],
                use_container_width=True,
                hide_index=True,
            )
            if detector_id == "burned_area":
                st.caption(
                    "Severity covers all valid pixels. The selected-area metric uses your separate candidate threshold and patch filter."
                )
            elif detector_id == "prepared_mask":
                st.info(
                    "Your input provides class membership, not severity. To estimate burn severity, supply calibrated NIR/SWIR before and after imagery and select Wildfire · burned area."
                )
        if result.report.get("validation"):
            st.subheader("Reference agreement")
            st.json(result.report["validation"], expanded=False)
        else:
            st.caption(
                "Validation status: no independent reference comparison supplied. The report states this explicitly."
            )
        if not result.mask.any():
            st.success("No candidates met the selected threshold and patch size.")
        st.download_button(
            "Download GIS results + maps (.zip)",
            st.session_state["bundle"],
            "geosense_results.zip",
            "application/zip",
        )
        with ZipFile(BytesIO(st.session_state["bundle"])) as archive:
            c1, c2 = st.columns(2)
            with c1:
                st.download_button(
                    "Download presentation map (PDF)",
                    archive.read("map.pdf"),
                    "geosense_map.pdf",
                    "application/pdf",
                )
            with c2:
                st.download_button(
                    "Download map + methods report (PDF)",
                    archive.read("research_report.pdf"),
                    "geosense_research_report.pdf",
                    "application/pdf",
                )
        with st.expander("Method and reproducibility report"):
            st.json(result.report)
except Exception as error:
    st.session_state.pop("result", None)
    st.session_state.pop("bundle", None)
    st.error(f"Analysis could not proceed: {error}")

st.divider()
st.caption(
    f"GeoSense AI v{__version__} · Research screening and presentation workspace. Thresholds require local validation. Open exported GeoTIFFs and GeoJSON directly in QGIS or ArcGIS."
)
