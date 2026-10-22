# Releasing GeoSense AI

The current release is an alpha research tool, not an operational alert service.
Use Python 3.10–3.12. CI checks Windows and Linux; remote CI must pass after push.

1. Create a clean virtual environment without system-site-packages.
2. Install with `python -m pip install -e ".[dev]" pip-audit`.
3. Run `python -m ruff check .`, `python -m ruff format --check .`,
   `python -m pytest -q`, and `python -m pip check`.
4. Run `python -m pip_audit`; review vulnerabilities rather than suppressing them.
5. Run `python -m build`, then `python scripts/build_source_release.py`.
6. Review the source ZIP inventory and test installation from the source archive
   in another clean environment. Check the wheel CLI with `geosense --help`.
7. Upload only the reviewed source files or source ZIP contents to GitHub.
   Do not upload the whole working directory. Keep generated analysis bundles,
   uploaded data, virtual environments and credentials out of Git history.

Version comes from `geosense/__init__.py`. Record changes in CHANGELOG.md.
The release script uses an allowlist and rejects symlinks. ZIP includes source,
tests, documentation and workflow files, with a separate SHA-256 checksum.
Dependencies have compatibility ranges, not a universal lockfile. Capture a
deployment-specific `pip freeze` after testing for reproducibility; do not reuse
a Windows environment lock as a claim of Linux compatibility.

The MIT license applies to project code. Verify redistribution rights separately
before adding datasets, screenshots containing personal information or models.
Never present synthetic demonstrations as measured detection performance.
