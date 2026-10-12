"""Color and film LUT math.

The 3D LUT maps gamma-encoded sRGB -> gamma-encoded sRGB.
The RAW decoder returns linear sRGB. Exposure and highlight compression happen
in linear light before encoding to sRGB and applying the LUT.
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.ndimage import map_coordinates
import yaml

LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def srgb_encode(linear: np.ndarray) -> np.ndarray:
    x = np.maximum(np.asarray(linear, dtype=np.float32), 0)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1 / 2.4) - 0.055).astype(np.float32)


def srgb_decode(encoded: np.ndarray) -> np.ndarray:
    x = np.maximum(np.asarray(encoded, dtype=np.float32), 0)
    return np.where(x <= 0.04045, x / 12.92, np.power((x + 0.055) / 1.055, 2.4)).astype(np.float32)


def highlight_compress(linear: np.ndarray, knee: float = 0.82) -> np.ndarray:
    """Smooth shoulder: identity below knee; smoothly maps bright values below 1.

    Continuous first derivative at knee. Applied to each sRGB-linear channel;
    this is intentionally a simple output-rendering approximation, not a
    spectral or scene-referred film model.
    """
    if not 0 < knee < 1:
        raise ValueError("knee must be in (0, 1)")
    x = np.maximum(linear, 0)
    return np.where(x <= knee, x, 1 - (1-knee) * np.exp(-(x-knee)/(1-knee))).astype(np.float32)


def load_profile(name: str, directory: Path | None = None) -> dict:
    if directory is None:
        directory = Path(__file__).resolve().parent / "profiles"
    path = directory / (name if name.endswith(".yaml") else name + ".yaml")
    if not path.exists():
        choices = ", ".join(sorted(x.stem for x in directory.glob("*.yaml")))
        raise ValueError(f"Unknown profile '{name}'. Available: {choices}")
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    validate_profile(data)
    return data


def validate_profile(profile: dict) -> None:
    if not isinstance(profile, dict) or "name" not in profile or "tone_points" not in profile:
        raise ValueError("Profile requires name and tone_points")
    pts = np.asarray(profile["tone_points"], dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 2 or pts.shape[0] < 3:
        raise ValueError("tone_points must have at least three [input, output] pairs")
    if not (np.all(np.diff(pts[:, 0]) > 0) and np.all(np.diff(pts[:, 1]) >= 0)):
        raise ValueError("tone_points x must increase and y cannot decrease")
    if pts[0, 0] != 0 or pts[-1, 0] != 1:
        raise ValueError("tone_points must span input [0, 1]")
    for key in ("shadow_tint", "highlight_tint"):
        if len(profile.get(key, [0, 0, 0])) != 3:
            raise ValueError(f"{key} must have three elements")
    matrix = np.asarray(profile.get("color_matrix", np.eye(3)))
    if matrix.shape != (3, 3):
        raise ValueError("color_matrix must be 3x3")


def rgb_to_hsv(rgb: np.ndarray) -> np.ndarray:
    """Fast vectorized RGB->HSV, hue in degrees."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    d = mx - mn
    s = np.divide(d, mx, out=np.zeros_like(d), where=mx > 1e-8)
    h = np.zeros_like(d)
    nonzero = d > 1e-8
    rm = nonzero & (mx == r)
    gm = nonzero & (mx == g) & ~rm
    bm = nonzero & ~rm & ~gm
    h[rm] = np.mod((g[rm] - b[rm]) / d[rm], 6.0) * 60
    h[gm] = ((b[gm] - r[gm]) / d[gm] + 2) * 60
    h[bm] = ((r[bm] - g[bm]) / d[bm] + 4) * 60
    return np.stack([h, s, mx], axis=-1)


def hsv_to_rgb(hsv: np.ndarray) -> np.ndarray:
    h = np.mod(hsv[..., 0], 360) / 60
    s = np.clip(hsv[..., 1], 0, 1)
    v = np.clip(hsv[..., 2], 0, 1)
    c = v * s
    x = c * (1 - np.abs(np.mod(h, 2) - 1))
    z = np.zeros_like(c)
    q = np.stack([c, x, z], axis=-1)
    choices = [q, np.stack([x, c, z], -1), np.stack([z, c, x], -1),
               np.stack([z, x, c], -1), np.stack([x, z, c], -1),
               np.stack([c, z, x], -1)]
    out = np.select([(h >= i)[:, None] & (h < i + 1)[:, None] for i in range(6)], choices, default=choices[0])
    return out + (v-c)[..., None]


def film_transform(rgb: np.ndarray, profile: dict) -> np.ndarray:
    """Procedural film-inspired transform on gamma-encoded sRGB values [0, 1].

    Shape [...,3]. Supports batches of LUT nodes as well as images.
    """
    x = np.clip(np.asarray(rgb, dtype=np.float32), 0, 1)
    shape = x.shape
    if shape[-1] != 3:
        raise ValueError("Expected RGB input with 3 channels")
    x = x.reshape(-1, 3)
    lum = x @ LUMA
    points = np.asarray(profile["tone_points"], dtype=np.float32)
    target = PchipInterpolator(points[:, 0], points[:, 1])(lum).astype(np.float32)
    saturation = float(profile.get("saturation", 1.0))
    y = target[:, None] + saturation * (x - lum[:, None])
    y = y @ np.asarray(profile.get("color_matrix", np.eye(3)), dtype=np.float32).T
    y = np.clip(y, 0, 1)

    if profile.get("hue_bands"):
        hsv = rgb_to_hsv(y)
        for band in profile["hue_bands"]:
            distance = np.abs((hsv[:, 0] - float(band["center"]) + 180) % 360 - 180)
            weight = np.exp(-0.5 * np.square(distance / float(band.get("width", 35))))
            # Avoid modifying near-neutral tones with ill-defined hues.
            weight *= np.clip(hsv[:, 1] / 0.2, 0, 1)
            hsv[:, 0] += weight * float(band.get("hue_shift", 0))
            hsv[:, 1] *= 1 + weight * (float(band.get("saturation", 1)) - 1)
        y = hsv_to_rgb(hsv)

    tint_lo = np.asarray(profile.get("shadow_tint", [0, 0, 0]), dtype=np.float32)
    tint_hi = np.asarray(profile.get("highlight_tint", [0, 0, 0]), dtype=np.float32)
    # Weighted tints fade at middle-gray so colors stay more stable near midtones.
    y += (np.maximum(0, 0.5-target) / 0.5)[:, None]**2 * tint_lo
    y += (np.maximum(0, target-0.5) / 0.5)[:, None]**2 * tint_hi
    return np.clip(y, 0, 1).reshape(shape).astype(np.float32)


def create_lut(profile: dict, size: int = 33) -> np.ndarray:
    if not 2 <= size <= 129:
        raise ValueError("LUT size must be between 2 and 129")
    axis = np.linspace(0, 1, size, dtype=np.float32)
    grid = np.stack(np.meshgrid(axis, axis, axis, indexing="ij"), -1)
    return film_transform(grid, profile)


def apply_lut(rgb: np.ndarray, lut: np.ndarray, chunk: int = 200_000) -> np.ndarray:
    """Trilinear interpolation using scipy. LUT indexed [red, green, blue, channel]."""
    values = np.asarray(rgb, dtype=np.float32)
    if values.shape[-1] != 3:
        raise ValueError("Expected RGB image")
    if lut.ndim != 4 or lut.shape[:3] != (lut.shape[0],) * 3 or lut.shape[3] != 3:
        raise ValueError("Expected cubic LUT of shape (N,N,N,3)")
    flat = values.reshape(-1, 3)
    out = np.empty_like(flat)
    steps = lut.shape[0] - 1
    for start in range(0, len(flat), chunk):
        stop = min(start + chunk, len(flat))
        coords = (np.clip(flat[start:stop], 0, 1) * steps).T
        for ch in range(3):
            out[start:stop, ch] = map_coordinates(lut[..., ch], coords, order=1,
                                                  mode="nearest", prefilter=False)
    return out.reshape(values.shape)


def export_cube(profile: dict, output: Path, size: int = 33) -> Path:
    lut = create_lut(profile, size)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        f.write(f'TITLE "raw2film {profile["name"]} (sRGB to sRGB)"\n')
        f.write(f"LUT_3D_SIZE {size}\nDOMAIN_MIN 0.0 0.0 0.0\nDOMAIN_MAX 1.0 1.0 1.0\n")
        # .cube stores red fastest, then green, then blue. Internal LUTs
        # are indexed [red, green, blue], so transpose only the grid axes.
        for r, g, b in lut.transpose(2, 1, 0, 3).reshape(-1, 3):
            f.write(f"{r:.8f} {g:.8f} {b:.8f}\n")
    return output
