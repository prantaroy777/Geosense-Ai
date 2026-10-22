"""Formal map and methods dossier with explicit provenance and caveats."""

from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)
from pypdf import PdfReader, PdfWriter
from .science import SEVERITY_SOURCE


def research_report(result, map_pdf):
    report = result.report
    metadata = report.get("presentation", {})
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="SmallGeo",
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#344e59"),
        )
    )
    styles["Title"].textColor = colors.HexColor("#173c48")
    story = []

    def para(text, style="BodyText"):
        story.append(Paragraph(escape(str(text)), styles[style]))
        story.append(Spacer(1, 7))

    para("Methods, evidence & limitations", "Title")
    para(metadata.get("title") or "GeoSense AI analysis", "Heading2")
    para(
        f"Analysis ID: {report.get('analysis_id', 'not assigned')} | Generated: {report['created_utc']}",
        "SmallGeo",
    )
    para("1. Interpretation", "Heading2")
    para(report["limitations"])
    if report.get("monitoring"):
        monitoring = report["monitoring"]
        para(
            f"Monitoring interval: {monitoring['reference_date']} to {monitoring['current_date']}. Common surveyed coverage: {monitoring['common_coverage_km2']:.3f} km². Reference event: {monitoring['reference_event_km2']:.3f} km²; current event: {monitoring['current_event_km2']:.3f} km²; net mapped change: {monitoring['net_change_km2']:+.3f} km²."
        )
    if report["detector"] == "burned_area":
        para(
            "Burn severity is an estimate of post-fire effects inferred from spectral change. It is not fire intensity, flame length, fire radiative power or a field measurement. Reference dNBR classes use 0.10, 0.27, 0.44 and 0.66 as lower bounds. Thresholds require local ecological and field validation."
        )
        para(
            "Severity classes cover all valid pixels independently of the candidate threshold and minimum-patch filter; the selected-area total can therefore differ from the sum of severity classes above low severity."
        )
    elif report.get("vector_product"):
        para(
            "This is an imported vector interpretation. Event attributes and any selected damage classes are supplied by the producer. No new satellite detection or fire-severity estimation has been performed. Raster outputs are display derivatives; reported areas are geodesic areas of vector unions, not sampled pixel estimates."
        )
    elif report["detector"] == "prepared_mask":
        para(
            "This input is an existing class raster. The selected value is mapped as supplied. Fire severity and fire intensity cannot be reconstructed from a binary mask. Confirm class semantics, acquisition period and producer methods before interpreting it as burned area."
        )
    para("2. Spatial processing", "Heading2")
    processing = report.get("processing") or {}
    if report.get("vector_product"):
        para(
            f"CRS: {report['crs']}. Event features: {report['polygon_count']}. Class field: {report.get('class_field') or 'single event class'}. AOI applied: {report['aoi_applied']}. Cross-class overlap is retained; within-class and overall union areas avoid double counting within each measurement."
        )
    else:
        para(
            f"CRS: {report['crs']}. Valid pixels: {report['valid_pixels']:,}. Candidate pixels: {report['detected_pixels']:,}. Threshold / selected class: {report['threshold']}. Minimum patch: {report['minimum_patch_pixels']} processed pixels. AOI applied: {report['aoi_applied']}."
        )
    precision_note = (
        "AOI clipping uses source vector geometry. Source digitisation and interpretation limit boundary precision."
        if report.get("vector_product")
        else "Pixel-center AOI selection and raster resolution limit boundary precision."
    )
    para(
        f"Selected geodesic area: {report['area_km2']:,.4f} km². Area calculated on WGS84 polygon geometry. {precision_note} No statistical confidence interval is available."
    )
    para(
        "Display pixels are for cartography only; all area statistics use source vector geometry."
        if report.get("vector_product")
        else processing.get(
            "note",
            "Native synthetic grid or direct in-memory scene; see input provenance.",
        )
    )
    for warning in report.get("presentation_warnings", []):
        para(warning)
    if processing:
        para(
            f"Source grid: {processing['source_width']} x {processing['source_height']}; processed grid: {processing['output_width']} x {processing['output_height']}; output pixel size: {processing['resolution']} in CRS units; crop: {processing['crop_bounds']}.",
            "SmallGeo",
        )
    para("3. Mapped class distribution", "Heading2")
    rows = [
        [
            "Class",
            "Display pixels" if report.get("vector_product") else "Pixels",
            "Area (km²)",
            "% event union" if report.get("vector_product") else "% valid area",
        ]
    ]
    for row in report.get("class_statistics", []):
        rows.append(
            [
                Paragraph(escape(row["label"]), styles["SmallGeo"]),
                f"{row['pixels']:,}",
                f"{row['area_km2']:,.3f}",
                f"{row['area_percent']:.2f}",
            ]
        )
    table = Table(rows, colWidths=[210, 80, 90, 90], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#173c48")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.HexColor("#f0f5f4"), colors.white],
                ),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ]
        )
    )
    story.extend([table, Spacer(1, 12)])
    para("4. Validation status", "Heading2")
    validation = report.get("validation")
    if validation:
        para(validation["note"])
        for key in [
            "reference",
            "evaluated_pixels",
            "precision",
            "recall",
            "f1",
            "iou",
            "true_positive",
            "false_positive",
            "false_negative",
            "true_negative",
        ]:
            para(f"{key.replace('_', ' ').title()}: {validation.get(key)}", "SmallGeo")
    else:
        para(
            "No independent reference comparison supplied. Software tests demonstrate implementation behavior, not real-world detection accuracy. Do not present this result as a validated hazard assessment."
        )
    story.append(PageBreak())
    if report.get("quality"):
        para("Data-quality findings", "Heading2")
        for finding in report["quality"]["findings"]:
            para(
                f"{finding['status'].upper()} - {finding['check']}: {finding['detail']}",
                "SmallGeo",
            )
    para("5. Provenance and reproducibility", "Heading2")
    for key in [
        "author",
        "institution",
        "source",
        "study_area",
        "before_date",
        "after_date",
        "notes",
    ]:
        para(
            f"{key.replace('_', ' ').title()}: {metadata.get(key) or 'Not supplied'}",
            "SmallGeo",
        )
    for key, source in report.get("inputs", {}).items():
        para(f"Input {key}: {source}", "SmallGeo")
    para(
        f"Current scene: {report['after']}; reference scene: {report['before'] or 'Not required'}. Synthetic: {report['synthetic']}. GeoSense AI {report['version']}.",
        "SmallGeo",
    )
    para("6. Before academic or operational use", "Heading2")
    para(
        "Verify source licensing and band calibration; record comparable acquisition dates; inspect cloud/shadow and no-data coverage; validate thresholds against independent labels; quantify sampling and reference uncertainty; review false positives and false negatives. A presentation layout alone does not establish scientific validity."
    )
    if report["detector"] == "burned_area":
        para(
            "Method reference: Copernicus EFFIS, Fire Severity, reference dNBR classes (adapted from Key & Benson 2006). "
            + SEVERITY_SOURCE,
            "SmallGeo",
        )
    buffer = BytesIO()

    def footer(canvas, doc):
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#52656c"))
        canvas.drawString(42, 24, "GeoSense AI | Reproducible environmental screening")
        canvas.drawRightString(A4[0] - 42, 24, f"Methods {doc.page}")

    SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=42,
        rightMargin=42,
        topMargin=40,
        bottomMargin=42,
    ).build(story, onFirstPage=footer, onLaterPages=footer)
    writer = PdfWriter()
    for pdf in [map_pdf, buffer.getvalue()]:
        for page in PdfReader(BytesIO(pdf)).pages:
            writer.add_page(page)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()
