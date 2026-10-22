"""Deterministic synthetic reflectance; not satellite observations."""

import numpy as np
from rasterio.crs import CRS
from rasterio.transform import from_origin
from rasterio.io import MemoryFile
from .raster import Scene


def demo_scenes():
    rng = np.random.default_rng(42)
    size = (160, 200)
    bands = {
        name: np.full(size, value, dtype="float32")
        + rng.normal(0, 0.005, size).astype("float32")
        for name, value in {
            "red": 0.08,
            "green": 0.12,
            "nir": 0.55,
            "swir1": 0.25,
            "swir2": 0.18,
        }.items()
    }
    # Permanent water and an invalid border exist in both dates.
    for name, value in {
        "red": 0.03,
        "green": 0.15,
        "nir": 0.03,
        "swir1": 0.02,
        "swir2": 0.02,
    }.items():
        bands[name][110:140, 10:70] = value
    after = {name: data.copy() for name, data in bands.items()}
    for name, value in {"red": 0.22, "nir": 0.16, "swir1": 0.32, "swir2": 0.45}.items():
        after[name][30:80, 35:95] = value
    for name, value in {
        "red": 0.03,
        "green": 0.18,
        "nir": 0.04,
        "swir1": 0.02,
        "swir2": 0.02,
    }.items():
        after[name][100:140, 90:160] = value
    bands["thermal"] = np.full(size, 295, dtype="float32")
    after["thermal"] = bands["thermal"].copy()
    after["thermal"][40:60, 45:65] = 350
    bands["mask"] = np.zeros(size, dtype="float32")
    after["mask"] = np.zeros(size, dtype="float32")
    after["mask"][30:80, 35:95] = 1
    valid = np.ones(size, dtype=bool)
    valid[:5] = False
    for values in [bands, after]:
        for data in values.values():
            data[~valid] = np.nan
    transform = from_origin(400000, 5800000, 20, 20)
    crs = CRS.from_epsg(32633)
    return (
        Scene(bands, valid.copy(), transform, crs, "Synthetic before", True),
        Scene(after, valid.copy(), transform, crs, "Synthetic after", True),
    )


def scene_bytes(scene):
    with MemoryFile() as mem:
        with mem.open(
            driver="GTiff",
            height=scene.shape[0],
            width=scene.shape[1],
            count=len(scene.bands),
            dtype="float32",
            crs=scene.crs,
            transform=scene.transform,
            nodata=np.nan,
            compress="deflate",
        ) as dst:
            dst.update_tags(GEOSENSE_SYNTHETIC="true" if scene.synthetic else "false")
            for i, (name, values) in enumerate(scene.bands.items(), 1):
                dst.write(values, i)
                dst.set_band_description(i, name)
        return mem.read()
