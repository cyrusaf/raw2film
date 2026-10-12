"""RAW -> exposure/shoulder -> sRGB -> profile LUT -> grain -> JPEG."""
from __future__ import annotations

from functools import lru_cache
import hashlib
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter

from .color import srgb_encode, highlight_compress, create_lut, apply_lut, load_profile
from .io import load_linear_rgb, validate_output_paths, write_jpeg


def auto_exposure_ev(linear: np.ndarray, target: float = 0.18) -> float:
    """Conservative optional exposure adjustment based on 50th percentile.

    It is *not* a scene recognizer; metering can be wrong for snow or night.
    """
    sample = linear[::max(1, linear.shape[0] // 300), ::max(1, linear.shape[1] // 300)]
    luma = sample @ np.array([0.2126, .7152, .0722], dtype=np.float32)
    median = max(float(np.median(luma)), 0.001)
    return float(np.clip(np.log2(target / median), -2, 2))


def apply_grain(rgb: np.ndarray, amount: float, seed: int = 42) -> np.ndarray:
    if amount <= 0:
        return rgb
    if amount > 1:
        raise ValueError("Grain amount must be between 0 and 1")
    rng = np.random.default_rng(seed)
    # Lightly correlated monochromatic grain, not per-channel pixel noise.
    noise = rng.standard_normal(rgb.shape[:2], dtype=np.float32)
    noise = gaussian_filter(noise, sigma=0.48)
    noise *= (1 / max(float(np.std(noise)), 0.001))
    lightness = rgb @ np.array([0.2126, .7152, .0722], dtype=np.float32)
    strength = amount * (0.6 + 0.6 * (1 - lightness))
    return np.clip(rgb + (noise * strength)[..., None], 0, 1).astype(np.float32)


@lru_cache(maxsize=16)
def _lut_for_profile(name: str, size: int = 33) -> np.ndarray:
    return create_lut(load_profile(name), size=size)


def mix_look(baseline: np.ndarray, transformed: np.ndarray, strength: float) -> np.ndarray:
    """Blend or amplify a look, limiting amplification at the RGB gamut edge.

    Above 100%, scale the color displacement from neutral with a smooth
    shoulder approaching the RGB boundary. Use one scale per pixel to retain
    color direction. This is an artistic control, not film-density calibration.
    """
    delta = transformed - baseline
    if strength <= 1:
        return np.clip(baseline + strength * delta, 0, 1)
    room = np.where(delta > 0, 1 - baseline, baseline)
    limit = np.full_like(delta, np.inf)
    np.divide(room, np.abs(delta), out=limit, where=np.abs(delta) > 1e-8)
    headroom = np.maximum(np.min(limit, axis=-1, keepdims=True) - 1, 0)
    extra = strength - 1
    # Rational shoulder: slope 1 at strength=1, asymptotic at the boundary.
    # Divide first to avoid inf/inf for identical baseline/styled pixels.
    fraction = np.ones_like(headroom)
    np.divide(extra, headroom + extra, out=fraction)
    scale = 1 + extra * (1 - fraction)
    return np.clip(baseline + scale * delta, 0, 1)


def develop(linear: np.ndarray, film: str = "neutral", exposure: float = 0.0,
            auto_exposure: bool = False, grain: bool = True,
            grain_multiplier: float = 1.0, strength: float = 1.0,
            seed: int = 42) -> np.ndarray:
    """Return display-referred gamma-encoded sRGB float32 in [0,1]."""
    if not 0 <= strength <= 3:
        raise ValueError("strength must be between 0 and 3")
    if not 0 <= grain_multiplier <= 10:
        raise ValueError("grain multiplier must be between 0 and 10")
    if linear.ndim != 3 or linear.shape[-1] != 3:
        raise ValueError("Expected (height,width,3) linear RGB image")
    ev = exposure + (auto_exposure_ev(linear) if auto_exposure else 0)
    adjusted = np.asarray(linear, dtype=np.float32) * np.float32(2 ** ev)
    baseline = srgb_encode(highlight_compress(adjusted))
    if film == "neutral":
        return baseline
    profile = load_profile(film)
    transformed = apply_lut(baseline, _lut_for_profile(film))
    result = mix_look(baseline, transformed, strength)
    if grain:
        salt = int.from_bytes(hashlib.blake2b(film.encode(), digest_size=4).digest(), "little")
        result = apply_grain(result, float(profile.get("grain", 0)) * grain_multiplier * min(strength, 1),
                             seed=seed ^ salt)
    return result


def render_file(input_path: str | Path, output_path: str | Path, film: str,
                exposure: float = 0.0, auto_exposure: bool = False,
                grain: bool = True, grain_multiplier: float = 1.0,
                strength: float = 1.0, max_edge: int | None = None,
                seed: int = 42) -> Path:
    validate_output_paths([input_path], [output_path])
    image = load_linear_rgb(input_path, max_edge)
    rendered = develop(image, film, exposure, auto_exposure, grain,
                       grain_multiplier, strength, seed)
    return write_jpeg(rendered, output_path)
