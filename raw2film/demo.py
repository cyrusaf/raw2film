"""Generate a procedural RGB chart for pipeline smoke-testing (NOT a film reference)."""
from pathlib import Path
import numpy as np
from .io import write_jpeg
from PIL import Image


def create_demo(output: str | Path, width: int = 1200, height: int = 680) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    u = np.linspace(0, 1, width, dtype=np.float32)[None, :]
    v = np.linspace(0, 1, height, dtype=np.float32)[:, None]
    # Smooth gradient sky and shadowed foreground to reveal tone shifts.
    image = np.empty((height, width, 3), dtype=np.float32)
    image[..., 0] = np.broadcast_to(.30 + .57 * u - .1 * v, (height, width))
    image[..., 1] = np.broadcast_to(.37 + .44 * u - .17 * v, (height, width))
    image[..., 2] = np.broadcast_to(.5 + .22 * u - .20 * v, (height, width))
    # Saturated subjects: green foliage, blue sky, orange-red facade and skin approximations.
    blocks = [(0, (.83, .53, .35)), (1, (.16, .49, .21)),
              (2, (.18, .37, .75)), (3, (.86, .38, .19)),
              (4, (.79, .76, .66)), (5, (.14, .17, .20))]
    bw = width // 8
    for i, rgb in blocks:
        x0 = int((i + 1) * width / 8 - bw * .36)
        x1 = min(width, x0 + int(bw * .7))
        y0, y1 = int(height*.50), int(height*.85)
        image[y0:y1, x0:x1, :] = rgb
    img = Image.fromarray(np.uint8(np.clip(image, 0, 1)*255), "RGB")
    img.save(output)
    return output
