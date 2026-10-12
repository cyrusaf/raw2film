"""A static, locally viewable HTML compare gallery."""
from __future__ import annotations
import html
from pathlib import Path
from .io import load_linear_rgb, write_jpeg
from .render import develop

FILMS = ["neutral", "portra400", "gold200", "classic_chrome", "classic_negative"]
DISPLAY = ["Neutral", "Kodak Portra 400", "Kodak Gold 200", "Classic Chrome", "Classic Negative"]


def make_gallery(input_path: str | Path, output: str | Path,
                 exposure: float = 0, auto_exposure: bool = False,
                 max_edge: int | None = 1600, grain: bool = True,
                 grain_multiplier: float = 1.0, strength: float = 1.0,
                 seed: int = 42) -> Path:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    image = load_linear_rgb(input_path, max_edge)
    cards = []
    for film, label in zip(FILMS, DISPLAY):
        filename = f"{film}.jpg"
        rendered = develop(image, film, exposure, auto_exposure, grain,
                           grain_multiplier, strength, seed)
        write_jpeg(rendered, output / filename)
        cards.append(f'<figure><img src="{filename}" alt="{html.escape(label)}" loading="lazy">'
                     f'<figcaption>{html.escape(label)}</figcaption></figure>')
    source = html.escape(Path(input_path).name)
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>raw2film comparison — {source}</title><style>
:root{{color-scheme:dark}}body{{font-family:system-ui,-apple-system,sans-serif;background:#161719;color:#eee;
margin:0 auto;max-width:1550px;padding:28px}}header{{margin-bottom:22px}}p{{color:#aaa}}
.gallery{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,440px),1fr));gap:24px}}
figure{{margin:0;background:#242628;border-radius:10px;overflow:hidden}}img{{display:block;width:100%;height:auto}}
figcaption{{padding:14px 18px;font-weight:600}}footer{{margin-top:30px;color:#888;font-size:13px}}
</style></head><body><header><h1>raw2film comparison</h1><p>Source: {source} · Film-inspired prototypes, not calibrated film reproductions</p></header>
<div class="gallery">{''.join(cards)}</div><footer>All images share the same RAW development and exposure settings.</footer></body></html>'''
    (output / "index.html").write_text(page, encoding="utf-8")
    return output / "index.html"
