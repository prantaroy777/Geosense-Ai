# Professional monitoring priorities

## Delivered in this iteration

- Coverage-aware dated vector comparisons: persistent, newly mapped, no longer mapped.
- Technical data-quality findings, independent of thematic accuracy claims.
- Local immutable result bundles with manifests and checksums.
- Saved-run review and download, with integrity verification.
- Exported inputs/coverage and methods notes for comparison reproducibility.

## Before public multi-user deployment

1. Isolated background workers, queueing, resource quotas, cancellation and progress.
2. Access control, encrypted storage, explicit retention and incident logging.
3. Sensor-specific ingest/calibration and benchmarked independent reference datasets.
4. Windowed native-resolution analysis, instead of relying on sampled large-area previews.
5. STAC-based discovery with explicit collection/product/licence constraints; no invented scene dates.
6. Versioned methods and environments, full source hashes, reviewer approval and signed releases.
7. Co-registration error and minimum-change uncertainty modelling before quantitative alerts.
8. User-configured monitoring schedules and alert thresholds only after methods and false-alarm rates are validated.

## Research basis

Copernicus rapid-mapping QC emphasizes completeness, accuracy, readability and consistency, and relates product revisions to quality review. This application adds transparent checks but does not implement or claim the full Copernicus acceptance process.
https://mapping.emergency.copernicus.eu/about/rapid-mapping-manual/quality-control/

USGS ECCOE separates geometric, radiometric and spatial quality assessment; import success is not a scientific accuracy assessment.
https://www.usgs.gov/calval/data-quality-assessment

STAC provides standardized spatial/temporal asset metadata and discovery. It is a future acquisition interface, not implemented by the local run manifest.
https://stacspec.org/en/about/stac-spec/

Sources reviewed 2026-10-22.
