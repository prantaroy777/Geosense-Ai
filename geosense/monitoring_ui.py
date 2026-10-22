"""Monitoring and local audit library, using explicit survey coverage."""

from datetime import date
from io import BytesIO
from zipfile import ZipFile
import hashlib
import json
import streamlit as st
from .monitoring import demo_products, monitoring_result
from .vector_ui import package_cached, layer_cached
from .quality import vector_quality
from .pipeline import export_bundle, map_bytes
from .run_store import save_run, list_runs, load_run


def product_upload(label, key):
    files = st.file_uploader(
        label,
        type=[
            "zip",
            "json",
            "geojson",
            "shp",
            "shx",
            "dbf",
            "prj",
            "cpg",
            "kml",
            "kmz",
        ],
        accept_multiple_files=True,
        key=key,
    )
    if not files:
        return None
    uploads = [(f.name, f.getvalue()) for f in files]
    package = package_cached(uploads)
    names = [entry["name"] for entry in package.layers]
    if not names:
        raise ValueError(f"{label}: no readable spatial layers.")
    idx = next(
        (
            i
            for i, entry in enumerate(package.layers)
            if entry["suggested_role"] == "event"
        ),
        0,
    )
    selected = st.selectbox("Event layer", names, index=idx, key=key + "_event")
    default = next(
        (entry["name"] for entry in package.layers if entry["suggested_role"] == "aoi"),
        None,
    )
    options = [None] + names
    coverage_name = st.selectbox(
        "Survey coverage layer",
        options,
        index=options.index(default),
        format_func=lambda x: x or "Select coverage (required)",
        key=key + "_coverage",
    )
    st.caption(
        "Coverage must describe where the product was actually surveyed, not just the event perimeter."
    )
    if coverage_name == selected:
        raise ValueError(
            "Choose a separate survey boundary, not the event layer itself."
        )
    if not coverage_name:
        return None
    events, evidence = layer_cached(uploads, selected, None, "")
    coverage, coverage_evidence = layer_cached(uploads, coverage_name, None, "")
    if coverage_evidence["invalid_skipped"] or coverage_evidence["empty_skipped"]:
        raise ValueError(
            "Coverage geometries were excluded during import. Repair and review the survey boundary before comparison."
        )
    return (
        events,
        coverage,
        {
            "event": evidence,
            "coverage": coverage_evidence,
            "package_sha256": package.sha256,
        },
    )


def save_controls(bundle, title, key):
    if st.button("Save this run to local library", key=key):
        saved = save_run(bundle, title)
        st.success(
            f"Saved immutable run {saved['run_id'][:12]} with checksum. Available in Monitoring & run library."
        )


def comparison():
    source_mode = st.radio(
        "Comparison inputs",
        ["Synthetic comparison", "Upload two monitoring products"],
        horizontal=True,
    )
    st.info(
        "Compare mapped extent inside shared surveyed coverage. A disappearance from the map is labelled 'No longer mapped', not recovery."
    )
    try:
        evidence = {}
        if source_mode == "Synthetic comparison":
            before, current, bc, cc = demo_products()
            st.warning(
                "Synthetic demonstration: shifted rectangles, not real environmental change."
            )
        else:
            columns = st.columns(2)
            with columns[0]:
                left = product_upload("Reference package / files", "monitor_before")
            with columns[1]:
                right = product_upload("Current package / files", "monitor_current")
            if left is None or right is None:
                return
            before, bc, evidence["reference"] = left
            current, cc, evidence["current"] = right
            for role in ["reference", "current"]:
                if evidence[role]["event"]["invalid_skipped"]:
                    raise ValueError(
                        "Invalid event geometries were excluded. Resolve them before interpreting change."
                    )
        c1, c2 = st.columns(2)
        with c1:
            start = st.date_input(
                "Reference observation date",
                value=date(2025, 8, 1)
                if source_mode == "Synthetic comparison"
                else None,
                key="reference_date_" + source_mode,
            )
        with c2:
            end = st.date_input(
                "Current observation date",
                value=date(2025, 8, 15)
                if source_mode == "Synthetic comparison"
                else None,
                key="current_date_" + source_mode,
            )
        title = st.text_input("Comparison title", value="Event extent monitoring")
        attribution = st.text_input(
            "Source / producer",
            value="Synthetic demonstration"
            if source_mode == "Synthetic comparison"
            else "",
        )
        analyst = st.text_input("Analyst")
        comparable = st.checkbox(
            "I confirm both products describe the same event variable and their coverage layers represent surveyed areas",
            value=source_mode == "Synthetic comparison",
        )
        signature = hashlib.sha256(
            json.dumps(
                [
                    source_mode,
                    evidence,
                    str(start),
                    str(end),
                    title,
                    attribution,
                    analyst,
                    comparable,
                ],
                sort_keys=True,
            ).encode()
        ).hexdigest()
        if st.session_state.get("monitor_signature") != signature:
            st.session_state.pop("monitor_result", None)
            st.session_state["monitor_signature"] = signature
        if st.button(
            "Compare mapped extent",
            type="primary",
            disabled=not comparable or start is None or end is None,
        ):
            with st.spinner("Comparing polygons inside common coverage…"):
                result, coverage, summary = monitoring_result(
                    before, current, bc, cc, start, end
                )
                if result is not None:
                    result.report["synthetic"] = source_mode == "Synthetic comparison"
                    result.report["inputs"] = evidence
                    result.report["quality"] = vector_quality(
                        current,
                        evidence.get("current", {}).get("event", {}),
                        attribution,
                        str(end),
                    )
                    result.report["reference_quality"] = vector_quality(
                        before,
                        evidence.get("reference", {}).get("event", {}),
                        attribution,
                        str(start),
                    )
                    result.report["comparison_confirmed_by_user"] = comparable
                    metadata = {
                        "title": title,
                        "source": attribution,
                        "author": analyst,
                        "before_date": str(start),
                        "after_date": str(end),
                        "notes": summary["interpretation"],
                    }
                    bundle = export_bundle(result, metadata, coverage)
                    output = BytesIO()
                    with (
                        ZipFile(BytesIO(bundle)) as original,
                        ZipFile(output, "w") as target,
                    ):
                        for name in original.namelist():
                            target.writestr(name, original.read(name))
                        for name, doc in [
                            ("reference_events", before),
                            ("current_events", current),
                            ("reference_coverage", bc),
                            ("current_coverage", cc),
                            ("shared_coverage", coverage),
                        ]:
                            target.writestr(name + ".geojson", json.dumps(doc))
                    bundle = output.getvalue()
                else:
                    bundle = None
                st.session_state["monitor_result"] = (result, coverage, summary, bundle)
        if "monitor_result" in st.session_state:
            result, coverage, summary, bundle = st.session_state["monitor_result"]
            st.dataframe(summary["classes"], hide_index=True)
            c1, c2, c3 = st.columns(3)
            c1.metric(
                "Reference event area", f"{summary['reference_event_km2']:,.3f} km²"
            )
            c2.metric("Current event area", f"{summary['current_event_km2']:,.3f} km²")
            c3.metric("Net mapped change", f"{summary['net_change_km2']:+,.3f} km²")
            st.caption(
                f"Compared coverage: {summary['common_coverage_km2']:,.3f} km². Outside common coverage is excluded from change calculations."
            )
            st.json(summary, expanded=False)
            if result is not None:
                st.image(map_bytes(result, context=coverage))
                st.dataframe(result.report["quality"]["findings"], hide_index=True)
                st.download_button(
                    "Download comparison and evidence",
                    bundle,
                    "monitoring_comparison.zip",
                    "application/zip",
                )
                save_controls(bundle, title, "save_monitor")
            else:
                st.success(
                    "Neither product maps an event inside shared coverage. No event-change map is needed."
                )
                st.download_button(
                    "Download zero-event comparison summary",
                    json.dumps(summary, indent=2),
                    "comparison_summary.json",
                    "application/json",
                )
    except Exception as error:
        st.session_state.pop("monitor_result", None)
        st.error(f"Comparison could not proceed: {error}")


def workspace():
    st.subheader("Monitoring & run library")
    compare_tab, library_tab = st.tabs(["Compare observations", "Saved runs"])
    with compare_tab:
        comparison()
    with library_tab:
        st.caption(
            "Local workspace storage only. Saved ZIPs include uploaded/derived data; they are not sent to a cloud service. No background monitoring or notifications are scheduled."
        )
        runs = list_runs()
        if not runs:
            st.info(
                "Save a completed package or comparison run to build your audit history."
            )
        else:
            st.dataframe(
                [
                    {
                        k: r.get(k)
                        for k in [
                            "run_id",
                            "title",
                            "saved_utc",
                            "method",
                            "area_km2",
                            "quality_status",
                        ]
                    }
                    for r in runs
                ],
                hide_index=True,
            )
            chosen = st.selectbox(
                "Open saved run",
                [r["run_id"] for r in runs],
                format_func=lambda rid: next(
                    r["title"] + " · " + r["saved_utc"]
                    for r in runs
                    if r["run_id"] == rid
                ),
            )
            try:
                manifest, bundle = load_run(chosen)
                st.success("Bundle checksum verified.")
                with ZipFile(BytesIO(bundle)) as archive:
                    st.image(archive.read("map.png"))
                    st.json(json.loads(archive.read("report.json")), expanded=False)
                st.download_button(
                    "Download saved bundle", bundle, chosen + ".zip", "application/zip"
                )
            except (OSError, ValueError) as error:
                st.error(str(error))
