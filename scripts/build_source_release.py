"""Build a source-only GitHub release; never sweep the workspace recursively."""

from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import hashlib
import re

ROOT = Path(__file__).resolve().parents[1]


def build():
    version = re.search(
        r'__version__ = "([^"]+)"', (ROOT / "geosense/__init__.py").read_text()
    )[1]
    files = {
        ROOT / name
        for name in (
            "app.py",
            "pyproject.toml",
            "MANIFEST.in",
            ".gitignore",
            "LICENSE",
            "README.md",
            "CONTRIBUTING.md",
            "SECURITY.md",
            "CHANGELOG.md",
            ".streamlit/config.toml",
            ".github/workflows/tests.yml",
        )
    }
    for directory, suffix in (
        ("geosense", ".py"),
        ("tests", ".py"),
        ("scripts", ".py"),
        ("docs", ".md"),
    ):
        files.update((ROOT / directory).rglob("*" + suffix))
    destination = ROOT / "dist" / f"geosense-ai-{version}-source.zip"
    destination.parent.mkdir(exist_ok=True)
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        for path in sorted(files):
            if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()):
                raise ValueError(f"Unsafe release path: {path}")
            archive.write(path, path.relative_to(ROOT).as_posix())
    checksum = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(".zip.sha256").write_text(
        f"{checksum}  {destination.name}\n", encoding="utf-8"
    )
    print(f"{destination}\n{len(files)} source files; SHA-256 {checksum}")
    return destination


if __name__ == "__main__":
    build()
