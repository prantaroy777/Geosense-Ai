"""Detector registry. Scores are indices, never calibrated probabilities."""

from dataclasses import dataclass
from typing import Callable
import numpy as np


def normalized(a, b):
    denominator = a + b
    return np.divide(
        a - b,
        denominator,
        out=np.full_like(a, np.nan),
        where=np.abs(denominator) > 1e-8,
    )


def ndvi(b):
    return normalized(b["nir"], b["red"])


def nbr(b):
    return normalized(b["nir"], b["swir2"])


def water(b):
    return normalized(b["green"], b["swir1"])


@dataclass(frozen=True)
class Detector:
    id: str
    title: str
    bands: tuple[str, ...]
    needs_before: bool
    threshold: float
    score_name: str
    description: str
    evaluate: Callable


REGISTRY: dict[str, Detector] = {}


def register(detector):
    if detector.id in REGISTRY:
        raise ValueError(f"Duplicate detector: {detector.id}")
    REGISTRY[detector.id] = detector
    return detector


register(
    Detector(
        "active_fire",
        "Active fire · thermal anomaly candidates",
        ("thermal",),
        False,
        330.0,
        "Brightness temperature (K)",
        "Experimental absolute thermal threshold. Input must be calibrated brightness temperature in Kelvin. Hot surfaces can cause false positives; this is not a contextual MODIS/VIIRS fire algorithm.",
        lambda a, b, t: (a["thermal"], a["thermal"] >= t),
    )
)


def vegetation_change(after, before, threshold):
    baseline = ndvi(before)
    score = baseline - ndvi(after)
    return score, (score >= threshold) & (baseline >= 0.5)


register(
    Detector(
        "prepared_mask",
        "Existing event mask · map selected class",
        ("mask",),
        False,
        1.0,
        "Class value",
        "Maps pixels equal to your selected class in an existing classification or event mask. Confirm the class meaning from the data provider. This does not detect a new event or infer its cause.",
        lambda a, b, t: (a["mask"], a["mask"] == t),
    )
)


register(
    Detector(
        "burned_area",
        "Wildfire · burned area",
        ("nir", "swir2"),
        True,
        0.27,
        "dNBR",
        "Before-minus-after NBR screens for burn-related change. Other land changes can mimic burns; this does not detect active fire.",
        lambda a, b, t: (nbr(b) - nbr(a), nbr(b) - nbr(a) >= t),
    )
)
register(
    Detector(
        "flood",
        "Flood · new surface water",
        ("green", "swir1"),
        True,
        0.1,
        "after MNDWI",
        "New optical water relative to a baseline (baseline MNDWI <= 0). Clouds, shadows and seasonal water need review; SAR is a future extension.",
        lambda a, b, t: (water(a), (water(a) >= t) & (water(b) <= 0)),
    )
)
register(
    Detector(
        "waterbody",
        "Waterbody mapping",
        ("green", "swir1"),
        False,
        0.1,
        "MNDWI",
        "Maps candidate surface water. A single image does not establish flooding.",
        lambda a, b, t: (water(a), water(a) >= t),
    )
)
for key, title in [
    ("forest_stress", "Forest · low vegetation index"),
    ("crop_health", "Crops · low vegetation index"),
]:
    register(
        Detector(
            key,
            title,
            ("nir", "red"),
            False,
            0.3,
            "NDVI",
            "Low NDVI screening only, not a diagnosis. Supply a forest/crop AOI to exclude other land cover. Season, bare soil and harvest affect results.",
            lambda a, b, t: (ndvi(a), ndvi(a) <= t),
        )
    )
for key, title in [
    ("deforestation", "Deforestation · canopy-loss candidates"),
    ("storm", "Storm · vegetation-disturbance candidates"),
]:
    register(
        Detector(
            key,
            title,
            ("nir", "red"),
            True,
            0.25,
            "NDVI decrease",
            "Screens NDVI decrease where baseline NDVI >= 0.5. Cannot attribute the cause to logging or storms. Use comparable seasons, a forest AOI and independent event evidence.",
            vegetation_change,
        )
    )
