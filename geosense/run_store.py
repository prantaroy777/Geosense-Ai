"""Local immutable run bundles, atomically published with integrity checks."""

from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4
from io import BytesIO
from zipfile import ZipFile
import hashlib
import json
import os
import re

DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "outputs" / "run_library"


def _manifest(directory):
    if (
        directory.is_symlink()
        or directory.resolve().parent != directory.parent.resolve()
    ):
        raise ValueError("Saved run path leaves the library.")
    for name in ("manifest.json", "results.zip"):
        if (directory / name).is_symlink():
            raise ValueError("Saved run contains a linked file.")
    data = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if (
        not isinstance(data, dict)
        or data.get("run_id") != directory.name
        or not isinstance(data.get("saved_utc"), str)
        or not isinstance(data.get("title"), str)
        or not isinstance(data.get("sha256"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", data["sha256"])
        or type(data.get("bytes")) is not int
        or data["bytes"] < 0
    ):
        raise ValueError("Saved run has invalid metadata.")
    datetime.fromisoformat(data["saved_utc"])
    return data


def save_run(bundle, title, root=None):
    root = Path(root) if root is not None else DEFAULT_ROOT
    with ZipFile(BytesIO(bundle)) as archive:
        report = json.loads(archive.read("report.json"))
    run_id = uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    pending = root / ("." + run_id)
    pending.mkdir()
    manifest = {
        "run_id": run_id,
        "title": str(title)[:200],
        "saved_utc": datetime.now(timezone.utc).isoformat(),
        "analysis_id": report.get("analysis_id"),
        "method": report.get("method"),
        "area_km2": report.get("area_km2"),
        "sha256": hashlib.sha256(bundle).hexdigest(),
        "bytes": len(bundle),
        "monitoring": report.get("monitoring"),
        "quality_status": report.get("quality", {}).get("status", "not assessed"),
    }
    (pending / "results.zip").write_bytes(bundle)
    (pending / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    os.replace(pending, root / run_id)
    return manifest


def list_runs(root=None):
    root = Path(root) if root is not None else DEFAULT_ROOT
    runs = []
    if not root.exists():
        return runs
    for directory in root.iterdir():
        if not re.fullmatch(r"[0-9a-f]{32}", directory.name) or not directory.is_dir():
            continue
        try:
            data = _manifest(directory)
            runs.append(data)
        except (OSError, ValueError):
            continue
    return sorted(runs, key=lambda r: r["saved_utc"], reverse=True)


def load_run(run_id, root=None):
    if not isinstance(run_id, str) or not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise ValueError("Invalid run identifier.")
    root = Path(root) if root is not None else DEFAULT_ROOT
    directory = root / run_id
    manifest = _manifest(directory)
    data = (directory / "results.zip").read_bytes()
    if (
        len(data) != manifest["bytes"]
        or hashlib.sha256(data).hexdigest() != manifest["sha256"]
    ):
        raise ValueError(
            "Saved bundle failed integrity verification; do not use this copy."
        )
    return manifest, data
