# Contributing

Vector products use separate modules: `vector_io.py` groups and normalizes packages, `vector_analysis.py` computes geometry-based summaries, and `vector_ui.py` provides the import workflow. Extend readers with explicit CRS/geometry contracts and tests for malformed archives, projected coordinates and attributes. Never reinterpret provider damage labels as newly calculated spectral severity. Preserve native vector measurements separately from display rasters.

Contributions are welcome. Open an issue describing the target phenomenon, data requirements, scientific method and expected outputs before proposing a substantial change. Keep processing independent of Streamlit so it remains testable and reusable.

## Development

Install `python -m pip install -e ".[dev]"`, then run `python -m pytest -q`. CI runs on Windows and Linux. Use small synthetic fixtures in tests; never commit satellite archives, credentials or private study boundaries. Pin a tested deployment environment separately from the package's supported dependency ranges.

## Add a detector

Add a `Detector` to `geosense/detectors.py` using `register`. Each evaluator takes `(after_bands, before_bands_or_none, threshold)` and returns `(score_array, boolean_candidate_array)` on the input grid. Declare required bands, whether a baseline is necessary, a default threshold, score units and limitations. Missing required bands and baseline checks are handled centrally. Registration makes the detector available in the UI and CLI.

```python
def evaluate(after, before, threshold):
    score = normalized(after["nir"], after["red"])
    return score, score >= threshold


register(
    Detector(
        "vegetation_cover",
        "Vegetation cover candidates",
        ("nir", "red"),
        False,
        0.5,
        "NDVI",
        "Land-cover screening; validate locally.",
        evaluate,
    )
)
```

If a new score has units outside the default index range, update threshold validation and map color limits in `pipeline.py` (thermal detection demonstrates this). For a larger plugin ecosystem, move score bounds, display ranges and input calibration metadata into the detector contract first.

## Pull request expectations

- Explain the scientific assumptions and include primary method references for new analyses.
- Test positive/negative examples, invalid pixels, missing bands and baseline requirements.
- For changed spatial processing, test CRS alignment, AOI handling and area calculation.
- Include a synthetic runnable example and update the input/output documentation.
- Separate benchmark accuracy on independently labelled data from passing software tests. Report dataset licenses, geographic/temporal coverage, precision/recall or IoU and limitations.
- Do not describe a spectral proxy as confirmed fire, flood, storm damage or deforestation. Add probability outputs only when calibration has been evaluated.

Code is licensed under MIT. Contributions must be compatible with that license. Dataset, imagery, model and third-party attribution rights remain separate. Never contribute material you do not have permission to redistribute.
