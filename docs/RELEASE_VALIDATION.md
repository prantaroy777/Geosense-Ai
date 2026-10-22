# Release validation — 0.4.0a1

Date: 2026-10-22. Local platform: Windows, Python 3.10.9.

- Installed dependencies in a new isolated `.venv-release`, without inherited
  Anaconda site-packages. NumPy 2.2.6, Rasterio 1.4.4, SciPy 1.15.3,
  Streamlit 1.65.0 and Matplotlib 3.10.9 were exercised.
- 55 tests passed, including synthetic raster uploads, vector exports,
  monitoring UI, invalid input, run integrity and small connected patches.
- Ruff lint and formatting checks passed. `pip check` found no broken requirements.
- Source distribution and wheel built successfully using isolated build tooling.
- GitHub CI is configured for Windows/Linux and Python 3.10, 3.11 and 3.12.
  These remote jobs have not been run locally; their results must be reviewed
  after publication. No macOS test claim is made.
- Rasterio/Affine emit pending-deprecation warnings; tests still pass.
- Dependency audit is **not clean**: 35 advisories remain for Pillow 12.3.0.
  Packaging-tool findings were fixed by updating pip and setuptools. See SECURITY.md
  for the upstream compatibility conflict. Counts are audit results, not a claim
  that every advisory is reachable through this application.

Source packaging excludes local data, generated PDFs, run libraries, logs and
virtual environments. The ZIP has a companion SHA-256 checksum. Review source
changes and third-party data rights before publishing. No GitHub repository or
release has been created by this task.

Passing software tests is not scientific validation. Accuracy, sensitivity to
geography/season, operational performance and emergency suitability have not
been established. Large rasters use bounded sampling and may miss small events.
