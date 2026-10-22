"""Reproduce the shipped visual demonstration without external data."""

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
from geosense.demo import demo_scenes
from geosense.pipeline import analyze, export_bundle

before, after = demo_scenes()
result = analyze(after, "burned_area", before)
metadata = {
    "title": "Post-fire vegetation effects | Synthetic demonstration",
    "author": "GeoSense AI demonstration",
    "institution": "Research workflow example",
    "study_area": "Synthetic landscape - no real event",
    "source": "Deterministic synthetic reflectance; no satellite observations",
    "before_date": "Synthetic baseline",
    "after_date": "Synthetic follow-up",
}
bundle = export_bundle(result, metadata)
output = Path("output/pdf")
output.mkdir(parents=True, exist_ok=True)
with ZipFile(BytesIO(bundle)) as archive:
    (output / "geosense_severity_map.pdf").write_bytes(archive.read("map.pdf"))
    (output / "geosense_research_report.pdf").write_bytes(
        archive.read("research_report.pdf")
    )
Path("outputs").mkdir(exist_ok=True)
Path("outputs/research_demo.zip").write_bytes(bundle)
print("Created map, methods report and GIS demo bundle.")
