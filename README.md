# GeoSense AI

**0.4.0a1 — experimental research release.** MIT-licensed code; input datasets retain their own licenses. Software tests do not establish detection accuracy or suitability for emergency decisions.

Release audit: automated tests pass, but the tested dependency stack has unresolved Pillow advisories because Streamlit requires Pillow <13. Use locally with trusted data; public deployment is not release-approved. See [validation evidence](docs/RELEASE_VALIDATION.md).

Quick start from the source folder (Python 3.10–3.12):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address=127.0.0.1
```

On Linux/macOS use `.venv/bin/python` instead. Start with **Synthetic demo**. The wheel installs the core library and `geosense` CLI; the browser application is included in the source distribution. See [release checks](docs/RELEASING.md), [security](SECURITY.md), and [contributing](CONTRIBUTING.md).

Automated Satellite-Based Geospatial Event Detection and Mapping.

An extensible Python research prototype that turns calibrated satellite band stacks into candidate masks, area statistics and QGIS/ArcGIS-compatible exports. Includes a browser interface, a command-line interface and deterministic synthetic scenes, so no data download or account is needed to try it.

## Monitoring and local audit library

Select **Monitoring & run library** to try a synthetic comparison or upload two dated vector products. Supply a separate survey-coverage layer for each product and confirm comparable event definitions. The tool intersects survey coverage before measuring newly mapped, persistent and no-longer-mapped event polygons. Observation dates must be explicit and increasing. Changes outside shared coverage are excluded, not treated as environmental improvement. Comparisons use all polygons in the selected event layer; prepare consistent filtered layers before comparison if your source mixes unrelated classes.

Quality findings report excluded geometries, duplicate polygons, overlap, missing date/attribution and an explicitly unverified scientific-accuracy status. Monitoring rejects excluded invalid event geometries and excluded coverage geometries. Technical checks are not Copernicus approval or independent accuracy validation.

Completed vector and monitoring results can be saved explicitly to `outputs/run_library`. Each local run contains an immutable bundle, timestamped manifest and SHA-256 checksum. Saved-run review verifies the bundle checksum before display/download. There is no cloud upload, scheduled polling, automated alerting, authentication or retention service. Storage is local and grows until managed by the workspace owner.

The monitoring ZIP also retains both normalized event layers, both survey boundaries and their common coverage. A zero-event comparison returns a JSON summary rather than fabricating a map. Source positional error or changed producer methods can create apparent boundary changes; no tolerance or significance model is applied.

## GIS vector packages

Select **GIS vector package** in the Data source sidebar. Upload the original ZIP (recommended), or select all component files together. The importer groups equivalent representations by filename stem, suggests `observedEvent` as the event layer and `areaOfInterest` as the study boundary, and lets you choose context layers and an optional provider-supplied class field.

Supported geometry: GeoJSON/JSON FeatureCollections (including legacy CRS metadata), Shapefile sets (`.shp`, `.shx`, `.dbf` and `.prj`), and simple KML/KMZ Points, LineStrings, Polygons and MultiGeometry. KMZ must contain one KML document. Missing Shapefile CRS requires an explicit EPSG code; it is never guessed. Coordinates are converted to WGS84. Invalid/empty geometries are excluded and counted in import evidence. No automatic geometric repair is applied.

The event workflow requires polygons. Points and lines can be context. Event area is measured from the polygon union, including holes, after optional vector AOI clipping. Within-class union areas are reported separately; different classes can overlap. Supplied attributes survive GeoJSON export. Display GeoTIFFs are cartographic derivatives and are not used to calculate the vector area. Optional intersection counts indicate possible exposure, not verified damage.

`.sld`, `.xml`, `.xlsx/.xls`, and `.osc` files appear in the inventory as style, metadata, spreadsheet or change-file companions. Their styles/formulas/changes are **not applied**. Network links in KML are not followed. Nested ZIP packages are not recursively imported. Six map classes, 100,000 features per layer, 3,000 archive entries and 750 MB combined uncompressed input are the current bounds. Only 2,000 intersecting context features are drawn; any truncation is disclosed and complete selected context layers remain in the export.

Validated locally against the supplied EMSR618 AOI01 MONIT01 package: its observed-event layer loaded through GeoJSON, Shapefile and KMZ; GeoJSON and KMZ union areas agree to numerical precision. This tests import consistency, not independent validation of the producer's event mapping.

## Research and presentation features

- A4 landscape map with classified legend, locally evaluated true north and geodesic scale, coordinates, CRS, schematic global extent locator, author/source credits and explicit evidence status.
- Editable presentation title, study-area name, author, institution, dates, attribution and methods notes. Titles and footer credits are abbreviated on the map when needed; the full values are retained in the report.
- Optional WGS84 GeoJSON context polygons, roads/rivers and place points. `name` properties provide labels for the first 30 features. Context is exported with the result. No online map data is silently fetched.
- Five reference dNBR burn-severity classes using [Copernicus EFFIS thresholds](https://forest-fire.emergency.copernicus.eu/about-effis/technical-background/fire-severity): below 0.10 unburned/regrowth, 0.10–0.27 low, 0.27–0.44 moderate-low, 0.44–0.66 moderate-high, >=0.66 high. Lower boundaries are inclusive. These classes are provisional spectral interpretations, not field-validated severity or fire intensity.
- `mapped_classes.tif`, `class_statistics.csv`, and a map-plus-methods `research_report.pdf` in every ZIP. The report includes provenance, selected threshold, pixel budget, analysis ID, class areas and limitations.
- Optional independent reference-mask agreement: confusion counts, precision, recall, F1 and intersection-over-union. Undefined ratios are null, not falsely reported as zero or perfect. The reference is aligned with nearest-neighbor sampling; metrics apply only to overlapping valid pixels on the processed grid.

**For your first formal map:** choose the matching analysis, supply imagery, expand Presentation settings to enter source/author/dates, run the analysis, review the class table, then download the presentation PDF or full research report. A binary mask can make a map of the supplied class; it cannot recover severity or intensity. For severity, use calibrated before/after NIR and SWIR2 imagery. The existing storm workflow remains a vegetation-change screen; no storm-intensity classes are invented.

Severity classes include all valid pixels, independently of the candidate threshold and patch filter. Class-table areas therefore need not equal the selected-area metric. Geographic map scale varies over the extent; the scale bar is locally evaluated, and wide-area maps should be reprojected and reviewed for publication. Place labels are limited but not automatically deconflicted.

CLI presentation options: `--metadata metadata.json --context context.geojson --reference labels.tif --reference-class 1`. Example metadata fields are `title`, `study_area`, `author`, `institution`, `source`, `before_date`, `after_date`, and `notes`.

See [docs/RESEARCH_WORKFLOW.md](docs/RESEARCH_WORKFLOW.md) for what makes an analysis defensible beyond map styling.

## Run locally

Python 3.10+ (3.11 or 3.12 recommended):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m streamlit run app.py
```

On Linux/macOS activate with `source .venv/bin/activate`. In the app choose **Synthetic demo**, choose an analysis, and click **Run analysis**. Sample before/after GeoTIFFs can be downloaded in the app. Synthetic outputs are demonstrations, not accuracy evidence.

Headless demo:

```powershell
python -m geosense.cli --demo --detector burned_area --output outputs/burned_area.zip
python -m pytest -q
```

## Analyses included

| Analysis | Required bands | Dates | Screening method |
|---|---|---|---|
| Burned area | NIR, SWIR2 | Before + after | dNBR >= threshold |
| Active fire candidates | Brightness temperature in Kelvin | Current | Experimental absolute thermal threshold |
| Flood | Green, SWIR1 | Before + after | After MNDWI >= threshold and baseline MNDWI <= 0 |
| Waterbody | Green, SWIR1 | Current | MNDWI >= threshold |
| Forest stress | NIR, red | Current | Low NDVI within a forest AOI |
| Crop health | NIR, red | Current | Low NDVI within a crop AOI |
| Deforestation candidates | NIR, red | Before + after | NDVI decrease where baseline NDVI >= 0.5 |
| Storm disturbance candidates | NIR, red | Before + after | Same vegetation-change baseline; cause requires external evidence |

These are transparent rule-based screening baselines, not trained AI models or validated disaster alerts. Storm and deforestation modules currently share a vegetation-change method. They cannot determine why vegetation changed. NDVI alone cannot diagnose plant health. Thermal thresholding is not a substitute for a contextual active-fire product. No confidence probabilities are invented.

## Real input contract

- Upload one north-up, georeferenced multiband GeoTIFF per date. Raw Sentinel SAFE, separate JP2 band files, SAR preprocessing and arbitrary RGB images are not supported in this alpha.
- Explicitly map spectral roles to band numbers. Exact descriptive role names can preselect mappings; arbitrary band order is never guessed.
- Use calibrated surface reflectance for optical indices. Dataset scale and offset metadata are applied, followed by the additional scale/offset supplied in the UI. Avoid applying calibration twice. Thermal inputs must be brightness temperature in Kelvin, not DN or Celsius.
- Baseline data is reprojected/resampled to the current grid with bilinear spectral resampling and nearest-neighbor validity resampling. Compare comparable seasons and acquisitions; alignment does not correct atmospheric or phenological differences.
- Nodata and nonfinite values are excluded. An optional embedded Sentinel-2 SCL band excludes classes 0, 1, 3, 8, 9, 10 and 11. Without it, supply imagery already masked for clouds/shadows. Class 7 remains unclassified and can require additional masking.
- Optional AOI: RFC 7946 WGS84 GeoJSON Polygon/MultiPolygon, Feature or FeatureCollection. Pixels are selected by their centers; boundary precision is raster-resolution dependent. Masks preserve the source extent with outside-AOI nodata.
- Large source rasters are supported through bounded reads: choose a processing budget (250,000 to 16 million pixels), or crop using bounds in the raster CRS before reading. Reduced-resolution processing uses nearest-neighbor sampling and explicitly labels approximate areas. Small features can be missed: crop a region small enough to fit the budget for native-resolution analysis. This is not full-resolution, whole-country streaming analysis. UI uploads remain limited to 200 MB; the CLI accepts larger files subject to available memory for compressed input bytes.

## Existing masks and classified rasters

Choose **Existing event mask · map selected class** for a binary burned-area raster, flood mask or other preclassified event product. Select the source band and class value (often 1 for an event, but confirm with the provider). No spectral baseline, thermal band or SCL band is needed. A 0/1 sample triggers a suggestion, never automatic scientific attribution. Sampled values are not exhaustive metadata. A source nodata value remains excluded even if it equals the selected class.

Large masks can be viewed at reduced resolution. The ZIP report records original/processed dimensions, pixel size, crop bounds and resampling. Minimum patch size refers to **processed pixels**, so use 1 to retain all sampled candidates. The CLI exposes `--max-pixels` and `--bounds WEST SOUTH EAST NORTH` for the same workflow.

## Outputs

Download one ZIP containing `candidate_mask.tif` (0 background, 1 candidate, 255 invalid), `analysis_score.tif`, `candidate_areas.geojson` (WGS84), `report.json`, `map.png` and `map.pdf`. GeoTIFFs retain the current scene's grid/CRS. Areas are calculated geodesically on WGS84 polygons, including holes. The report records method, thresholds, valid-pixel coverage, input hashes and explicit mappings for uploads. Scores are indices/temperature, not probabilities. GeoJSON replaces Shapefile in the initial release; QGIS can convert it when needed.

## Architecture and extensions

`geosense/raster.py` handles input and alignment; `detectors.py` defines a registry of detector contracts; `pipeline.py` owns AOI filtering, polygonization, area measurement and exports. `app.py` and `cli.py` call the same core. `demo.py` creates sample scenes. No QGIS installation or proprietary ArcGIS license is required.

See [CONTRIBUTING.md](CONTRIBUTING.md) for a detector example and [docs/ROADMAP.md](docs/ROADMAP.md) for contribution areas. Start with validated methods and benchmark data before adding model complexity.

Implementation references: [Rasterio reprojection](https://rasterio.readthedocs.io/en/stable/topics/reproject.html), [Rasterio features](https://rasterio.readthedocs.io/en/stable/topics/features.html), [Streamlit uploads](https://docs.streamlit.io/develop/api-reference/widgets/st.file_uploader).
