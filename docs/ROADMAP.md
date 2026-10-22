# Roadmap

## Implemented baseline

Eight screening workflows plus existing-mask/class extraction, binary sample guidance, explicit band mapping, nodata/SCL filtering, before/after alignment, AOI masking, minimum patch filtering, geodesic area, GeoTIFF/GeoJSON/PNG/PDF export, synthetic demo, CLI, UI, tests and CI configuration. Large inputs support bounded-resolution reads and bounding-box cropping before reading; full-resolution out-of-core national statistics remain future work.

## Highest-value next contributions

1. Real labelled benchmark cases and threshold calibration for burned-area and optical water detection.
2. Sensor adapters for Sentinel-2 SAFE/JP2 and Landsat metadata; per-band calibration and quality masks.
3. A Sentinel-1 SAR preprocessing and flood detector with terrain/shadow handling.
4. Validated active-fire product ingestion (e.g. VIIRS/MODIS) and contextual thermal analysis.
5. Land-cover masks, seasonal baselines and multi-date vegetation anomaly detection.
6. Storm-event metadata and validated disturbance models; separate logging/harvest/fire attribution from generic canopy change.
7. Tiled/windowed processing, background jobs, cancellation, caching and storage lifecycle controls for large scenes.
8. Interactive comparison maps, QGIS project generation, optional PyQGIS print layouts and richer cartography.
9. A versioned plugin API with declared score ranges, model artifacts and provenance; independently validated ML segmentation implementations.
10. Select a repository license, add issue/PR templates and publish a tested release with a dependency lockfile.

Public hosting needs separate work on upload isolation, quotas, authentication, error privacy, concurrency and worker resource limits. The current application is intended for local use.
