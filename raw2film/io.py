"""RAW and ordinary sRGB image input, JPEG output with embedded sRGB ICC.

RAW: rawpy demosaics in linear sRGB at 16 bits with camera WB, no automatic
brightening, and gamma=(1,1). The decoder output is normalized to [0,1].
Normal JPEG/PNG: assumed gamma-encoded sRGB, decoded into linear sRGB.
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
from PIL import Image, ImageCms, ImageOps

from .color import srgb_decode

RAW_EXTENSIONS = {".arw", ".dng", ".cr2", ".cr3", ".nef", ".raf", ".orf", ".rw2"}
RGB_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}


def load_linear_rgb(path: str | Path, max_edge: int | None = None) -> np.ndarray:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    if max_edge is not None and max_edge <= 0:
        raise ValueError("max-edge must be positive")
    if path.suffix.lower() in RAW_EXTENSIONS:
        try:
            import rawpy
        except ImportError as exc:
            raise RuntimeError("RAW processing needs rawpy. Install with `pip install rawpy`.") from exc
        with rawpy.imread(str(path)) as raw:
            # output_color = sRGB selects LibRaw's camera->sRGB color matrix;
            # gamma=(1,1) produces linear-light values, not encoded sRGB.
            arr = raw.postprocess(
                output_color=rawpy.ColorSpace.sRGB,
                gamma=(1, 1), output_bps=16,
                no_auto_bright=True, use_camera_wb=True,
                bright=1.0,
            )
        image = arr.astype(np.float32) / 65535.0
        del arr
        if max_edge is not None and max(image.shape[:2]) > max_edge:
            # Resize in linear-light space to preserve photographic response.
            from scipy.ndimage import zoom
            factor = max_edge / max(image.shape[:2])
            image = zoom(image, (factor, factor, 1), order=1).astype(np.float32)
        return image
    if path.suffix.lower() not in RGB_EXTENSIONS:
        raise ValueError(f"Unsupported input extension: {path.suffix}")
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        if "icc_profile" in im.info:
            try:
                src = ImageCms.ImageCmsProfile(__import__("io").BytesIO(im.info["icc_profile"]))
                dst = ImageCms.createProfile("sRGB")
                im = ImageCms.profileToProfile(im.convert("RGB"), src, dst,
                                               outputMode="RGB")
            except (OSError, ValueError, TypeError):
                # Some images contain invalid ICC metadata; this fallback
                # assumes sRGB (documented rather than silent conversion).
                im = im.convert("RGB")
        else:
            im = im.convert("RGB")
        if max_edge is not None:
            im.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        srgb = np.asarray(im, dtype=np.float32) / 255.0
    return srgb_decode(srgb)


def write_jpeg(srgb: np.ndarray, output: str | Path, quality: int = 94) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    arr = np.uint8(np.round(np.clip(srgb, 0, 1) * 255))
    img = Image.fromarray(arr, "RGB")
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    img.save(output, "JPEG", quality=quality, subsampling=0, icc_profile=icc)
    return output
