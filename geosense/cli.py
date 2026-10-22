"""Headless interface, using the same pipeline as the UI."""

import argparse
from . import __version__
import hashlib
import json
from pathlib import Path
from .demo import demo_scenes
from .detectors import REGISTRY
from .pipeline import analyze, export_bundle
from .raster import read_scene


def main():
    parser = argparse.ArgumentParser(description="GeoSense AI satellite screening")
    parser.add_argument(
        "--version", action="version", version=f"GeoSense AI {__version__}"
    )
    parser.add_argument("--detector", choices=list(REGISTRY), default="burned_area")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--after", type=Path)
    parser.add_argument("--before", type=Path)
    parser.add_argument(
        "--bands", help='JSON role-to-band mapping, e.g. {"nir":3,"swir2":5}'
    )
    parser.add_argument(
        "--before-bands", help="Separate baseline band mapping (defaults to --bands)"
    )
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--offset", type=float, default=0.0)
    parser.add_argument("--scl-band", type=int)
    parser.add_argument("--max-pixels", type=int, default=1_000_000)
    parser.add_argument(
        "--bounds",
        type=float,
        nargs=4,
        metavar=("WEST", "SOUTH", "EAST", "NORTH"),
        help="Crop bounds in each raster's CRS",
    )
    parser.add_argument("--threshold", type=float)
    parser.add_argument("--min-pixels", type=int, default=9)
    parser.add_argument("--aoi", type=Path)
    parser.add_argument(
        "--metadata",
        type=Path,
        help="JSON presentation fields: title, author, source, study_area, acquisition dates",
    )
    parser.add_argument(
        "--context", type=Path, help="WGS84 GeoJSON for map context and place labels"
    )
    parser.add_argument(
        "--reference",
        type=Path,
        help="Independent single-band class raster for pixel agreement",
    )
    parser.add_argument("--reference-class", type=float, default=1)
    parser.add_argument("--output", type=Path, default=Path("outputs/results.zip"))
    args = parser.parse_args()
    try:
        provenance = {}
        if args.demo:
            before, after = demo_scenes()
        else:
            if not args.after or not args.bands:
                parser.error("Use --demo or supply --after and --bands.")
            mapping = json.loads(args.bands)

            def load(path, roles):
                data = path.read_bytes()
                provenance[path.name] = {
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "bands": roles,
                    "scale": args.scale,
                    "offset": args.offset,
                    "scl_band": args.scl_band,
                }
                return read_scene(
                    data,
                    roles,
                    path.name,
                    args.scale,
                    args.offset,
                    args.scl_band,
                    max_pixels=args.max_pixels,
                    bounds=args.bounds,
                )

            after = load(args.after, mapping)
            before = (
                load(
                    args.before,
                    json.loads(args.before_bands) if args.before_bands else mapping,
                )
                if args.before
                else None
            )
        aoi = json.loads(args.aoi.read_text(encoding="utf-8")) if args.aoi else None
        result = analyze(
            after, args.detector, before, args.threshold, aoi, args.min_pixels
        )
        result.report["inputs"] = provenance
        metadata = (
            json.loads(args.metadata.read_text(encoding="utf-8"))
            if args.metadata
            else None
        )
        context = (
            json.loads(args.context.read_text(encoding="utf-8"))
            if args.context
            else None
        )
        if args.reference:
            from .science import compare_reference

            data = args.reference.read_bytes()
            reference = read_scene(
                data, {"mask": 1}, args.reference.name, max_pixels=args.max_pixels
            )
            result.report["validation"] = compare_reference(
                result, reference, args.reference_class
            )
            result.report["validation"]["sha256"] = hashlib.sha256(data).hexdigest()
            result.report["validation"]["processing"] = reference.processing
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(export_bundle(result, metadata, context))
        print(
            f"Wrote {args.output.resolve()} | candidate area {result.report['area_km2']:.3f} km²"
        )
    except (ValueError, OSError, KeyError) as error:
        parser.exit(2, f"Error: {error}\n")


if __name__ == "__main__":
    main()
