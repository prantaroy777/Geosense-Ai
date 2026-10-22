"""Explicit band mapping, masked reads, and baseline alignment."""

from dataclasses import dataclass
import numpy as np
import rasterio
from rasterio.io import MemoryFile
from rasterio.warp import reproject, Resampling
from rasterio.windows import from_bounds, Window
from affine import Affine
from math import sqrt

MAX_PIXELS = 16_000_000


@dataclass
class Scene:
    bands: dict
    valid: np.ndarray
    transform: object
    crs: object
    name: str
    synthetic: bool = False
    processing: dict = None

    @property
    def shape(self):
        return self.valid.shape


def inspect_raster(payload):
    with MemoryFile(payload) as mem, mem.open() as src:
        sample = src.read(
            1, out_shape=(min(256, src.height), min(256, src.width)), masked=True
        )
        values = np.unique(sample.compressed())
        return {
            "width": src.width,
            "height": src.height,
            "bands": src.count,
            "crs": str(src.crs),
            "resolution": list(src.res),
            "descriptions": list(src.descriptions),
            "nodata": src.nodata,
            "bounds": list(src.bounds),
            "pixels": src.width * src.height,
            "sample_values": values[:30].tolist(),
            "binary_sample": bool(len(values) and set(values.tolist()) <= {0, 1}),
            "sample_note": "Sample only; not an exhaustive classification of the raster.",
        }


def read_scene(
    payload,
    mapping,
    name="Uploaded scene",
    scale=1.0,
    offset=0.0,
    scl_band=None,
    max_pixels=1_000_000,
    bounds=None,
):
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError("Select at least one spectral band.")
    if not np.isfinite(scale) or not np.isfinite(offset):
        raise ValueError("Scale and offset must be finite.")
    if type(max_pixels) is not int or not 1 <= max_pixels <= MAX_PIXELS:
        raise ValueError(
            "Processing budget must be an integer between 1 and 16 million pixels."
        )
    indices = list(mapping.values()) + ([scl_band] if scl_band is not None else [])
    if any(type(index) is not int for index in indices):
        raise ValueError("Band numbers must be integers.")
    with MemoryFile(payload) as mem, mem.open() as src:
        if not src.crs:
            raise ValueError(
                "The GeoTIFF has no CRS. Assign its correct CRS in QGIS first."
            )
        if (
            src.transform.b != 0
            or src.transform.d != 0
            or src.transform.a <= 0
            or src.transform.e >= 0
        ):
            raise ValueError(
                "Use a north-up raster. Warp rotated/flipped imagery in QGIS before uploading."
            )
        if not 1 <= max_pixels <= MAX_PIXELS:
            raise ValueError(
                "Processing budget must be between 1 and 16 million pixels."
            )
        if len(set(mapping.values())) != len(mapping):
            raise ValueError("Each spectral role must use a different band.")
        if any(i < 1 or i > src.count for i in indices):
            raise ValueError("Band numbers must be within the uploaded raster.")
        if scl_band in mapping.values():
            raise ValueError(
                "The SCL classification band cannot also be a spectral band."
            )
        window = Window(0, 0, src.width, src.height)
        if bounds is not None:
            if (
                len(bounds) != 4
                or not np.isfinite(bounds).all()
                or bounds[0] >= bounds[2]
                or bounds[1] >= bounds[3]
            ):
                raise ValueError(
                    "Crop bounds must be west, south, east, north in the raster CRS."
                )
            requested = from_bounds(*bounds, transform=src.transform)
            try:
                window = window.intersection(requested).round_offsets().round_lengths()
            except rasterio.errors.WindowError:
                raise ValueError("Crop bounds do not overlap the raster.") from None
            if window.width < 1 or window.height < 1:
                raise ValueError(
                    "Crop bounds must cover at least one raster pixel in each dimension."
                )
        factor = max(1.0, sqrt(window.width * window.height / max_pixels))
        height, width = (
            max(1, int(window.height / factor)),
            max(1, int(window.width / factor)),
        )
        transform = src.window_transform(window) * Affine.scale(
            window.width / width, window.height / height
        )
        reduced = height < window.height or width < window.width
        processing = {
            "source_width": src.width,
            "source_height": src.height,
            "output_width": width,
            "output_height": height,
            "reduced_resolution": reduced,
            "crop_bounds": bounds,
            "resampling": "nearest",
            "resolution": [abs(transform.a), abs(transform.e)],
            "note": "Nearest-neighbor sampling can miss small features. Areas describe the processed grid, not native-resolution totals."
            if reduced
            else "Native-resolution processing.",
        }
        bands = {}
        valid = np.ones((height, width), dtype=bool)
        for role, index in mapping.items():
            raw = src.read(
                index,
                window=window,
                out_shape=(height, width),
                masked=True,
                resampling=Resampling.nearest,
            ).astype("float32")
            # Dataset calibration is applied before optional user calibration.
            values = (
                raw.filled(np.nan) * src.scales[index - 1] + src.offsets[index - 1]
            ) * scale + offset
            valid &= np.isfinite(values)
            bands[role] = values
        if scl_band:
            scl = src.read(
                scl_band,
                window=window,
                out_shape=(height, width),
                masked=True,
                resampling=Resampling.nearest,
            )
            valid &= ~np.ma.getmaskarray(scl) & np.isin(scl.data, [2, 4, 5, 6, 7])
        for values in bands.values():
            values[~valid] = np.nan
        return Scene(
            bands,
            valid,
            transform,
            src.crs,
            name,
            src.tags().get("GEOSENSE_SYNTHETIC") == "true",
            processing,
        )


def align_scene(scene, target):
    if (
        scene.crs == target.crs
        and scene.transform == target.transform
        and scene.shape == target.shape
    ):
        return scene
    bands = {}
    for role, values in scene.bands.items():
        dest = np.full(target.shape, np.nan, dtype="float32")
        reproject(
            values,
            dest,
            src_transform=scene.transform,
            src_crs=scene.crs,
            dst_transform=target.transform,
            dst_crs=target.crs,
            src_nodata=np.nan,
            dst_nodata=np.nan,
            resampling=Resampling.bilinear,
        )
        bands[role] = dest
    valid_mask = np.zeros(target.shape, dtype="uint8")
    reproject(
        scene.valid.astype("uint8"),
        valid_mask,
        src_transform=scene.transform,
        src_crs=scene.crs,
        dst_transform=target.transform,
        dst_crs=target.crs,
        resampling=Resampling.nearest,
    )
    valid = (valid_mask == 1) & np.logical_and.reduce(
        [np.isfinite(v) for v in bands.values()]
    )
    for values in bands.values():
        values[~valid] = np.nan
    return Scene(
        bands,
        valid,
        target.transform,
        target.crs,
        scene.name,
        scene.synthetic,
        scene.processing,
    )
