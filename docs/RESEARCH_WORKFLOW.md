# From screening to defensible environmental evidence

## What the current version does

GeoSense AI supplies reproducible index/class screening, bounded-resolution or cropped raster reads, geodesic vector-area summaries, reference-mask agreement and formal map/report exports. Contributors can use the detector registry without duplicating UI and export code. Cartography, scientific interpretation and reporting are separate modules.

## Concepts that must stay separate

- Burned area: where a product or method marks burned pixels.
- Burn severity: ecological effects inferred here from before-minus-after NBR, with provisional EFFIS reference bins.
- Fire intensity: energy-release behavior. A binary mask and dNBR do not measure intensity. Adding calibrated FRP product ingestion would be a separate feature.
- Storm disturbance: vegetation loss coincident with an event. Attribution requires timing, meteorological evidence and independent labels. The current NDVI-change screen cannot establish storm cause or storm intensity.
- Low vegetation index: a screening signal influenced by land cover, season, harvest, soils and water, not a diagnosis of forest/crop disease.

## Research workflow

1. Define event, question, spatial/temporal extent and target variable before choosing an index.
2. Record sensor, processing level, acquisition dates, reflectance calibration, QA filtering and data licence. A filename is not a source citation.
3. Choose comparable pre/post dates; inspect co-registration, clouds, shadows and phenology. Use field context and an appropriate land-cover boundary.
4. Choose native-resolution local processing for detailed estimates. A nearest-sampled continental overview is not a native-resolution area inventory.
5. Treat default thresholds as hypotheses. Validate against representative independent reference data, stratified across severity/land cover. Avoid training/test or spatial leakage.
6. Review omission/commission errors and uncertainty from labels, sampling and boundaries. Pixel metrics alone do not establish uncertainty bounds for total area.
7. Export the methods report with the map. Archive source identifiers/hashes, input settings, class definitions, software environment and validation data.

## Next engineering milestones

Prioritize these over adding unvalidated detector names:

1. Sensor-aware SAFE/JP2/Landsat ingestion, per-band calibration and robust QA masks.
2. Out-of-core full-resolution computation and exact streaming class statistics for national products. Current bounded reads are an explicitly labelled overview alternative.
3. A validated Sentinel-1 flood chain and terrain/shadow exclusion.
4. FRP/active-fire product adapters, retaining product QA and units, without translating temperature thresholds into physical fire intensity.
5. Multi-date seasonal vegetation baselines, matched controls and event attribution.
6. Benchmark datasets with licences, independent validation protocols, uncertainty estimation and published performance by region.
7. Tiled interactive mapping with draw-to-crop, asynchronous jobs/cancellation and authenticated storage for multi-user deployment.
8. Cartographic collision avoidance, purpose-selected map projections and optional QGIS project/layout export.

## Extension contracts

`science.py`: owns class definitions, geodesic class tables and reference comparisons. Keep scientific categories explicitly separate from UI display settings.

`cartography.py`: produces the same layout for preview, PNG and PDF. Add context styles and label placement here; preserve attribution and uncertainty labels.

`reporting.py`: creates a ReportLab methods dossier and appends it to the map. Reports must preserve absent information as absent rather than invent provenance or validation.

Method reference: Copernicus EFFIS Fire Severity, https://forest-fire.emergency.copernicus.eu/about-effis/technical-background/fire-severity (accessed 2026-10-22). The application uses the published reference bins, not the full EFFIS compositing/operational production chain.
