# raw2film v0.1

A minimal, **working Python command-line RAW developer with configurable photographic looks**. It renders Sony a7 III `.ARW` photographs (and other rawpy-supported camera RAW formats) with four procedural, editable film-inspired color looks:

- Kodak **Portra 400** (`portra400`)
- Kodak **Gold 200** (`gold200`)
- Fujifilm **Classic Chrome** (`classic_chrome`)
- Fujifilm **Classic Negative** (`classic_negative`)

Despite the project name, the engine is not restricted to film emulation: new looks can express any photographic color treatment. The CLI supports `--look` (with `--film` and `--stock` aliases).

These are **early artistic approximations**, not officially licensed, measured, or scientifically calibrated recreations of the named stocks/simulations. Color results depend on the RAW developer, camera and lighting. This software is not affiliated with Kodak or Fujifilm.

## Quick start (macOS / Linux)

Requires **Python 3.10+**. In the unzipped project directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[test]"

# Verify the program without needing a RAW file:
raw2film demo --output ./demo
open ./demo/gallery/index.html  # macOS

# Render a Sony RAW:
raw2film render DSC01234.ARW --look portra400 --output ./portra.jpg

# Make a gallery comparing all four looks + a neutral render:
raw2film compare DSC01234.ARW --output ./comparison
open ./comparison/index.html

# Render an entire folder:
raw2film batch ./raws --look gold200 --output ./rendered

# Export color+tone LUT (excludes RAW development and grain):
raw2film export-lut --look classic_chrome --size 33 --output ./classic_chrome.cube

# Run automated tests:
pytest -q
```

If `raw2film` is not on PATH, use `python -m raw2film` instead. Python dependencies are listed in `pyproject.toml`. For quick previews, append `--max-edge 1800` to `render`, or use the default 1600-pixel `compare` previews. The full-resolution rendering may use substantial RAM.

### CLI options

```sh
raw2film render path/to/photo.ARW --look portra400 --exposure +0.3
raw2film render photo.ARW --look gold200 --auto-exposure --strength 0.8
raw2film render photo.ARW --look gold200 --no-grain
raw2film render photo.ARW --look portra400 --grain-multiplier 1.5 --seed 42
raw2film compare photo.ARW --exposure -0.3 --max-edge 1600
raw2film batch ./raws --look classic_negative --max-edge 2500
```

`--auto-exposure` uses a simple median-luminance estimate, capped at +/-2 stops. It is deliberately **off by default** because night scenes and high-key subjects fool simple metering; the default is the camera exposure with no arbitrary auto-brightening. Camera white balance is used by default for RAW files. Grain is deterministic for a given input, profile, and seed.

## Processing pipeline

1. **Decode RAW**: `rawpy`/LibRaw demosaics and applies camera WB and camera-to-sRGB color conversion, returning 16-bit **linear-light sRGB** (no rawpy auto-brightening, `gamma=(1,1)`). Standard JPEG/PNG inputs are treated as display-sRGB and decoded to linear-light first; embedded ICC profiles are converted when possible.
2. **Linear exposure**: multiply pixels by `2 ** EV`; optionally auto-meter the scene.
3. **Output shoulder**: a smooth highlight compression above a linear-light knee. This is a simple output transform, **not** full HDR reconstruction or actual chemical film response. Some highlight information may already be clipped by LibRaw.
4. **Color encode**: convert linear sRGB to standard nonlinear sRGB transfer curve.
5. **Film LUT**: apply a 33x33x33 3D LUT, generated from the YAML profile. The LUT contains a monotonic PCHIP luminance curve, chroma adjustment, 3x3 color matrix, selective hue/saturation operations, and luminance-weighted shadow/highlight tints.
6. **Finishing**: add subtle monochromatic, spatially correlated, luminance-dependent grain as configured. Fujifilm looks have grain disabled by default.
7. **Export**: write JPEG with an embedded sRGB ICC profile, leaving the original untouched.

**The `.cube` LUT uses display-referred, gamma-encoded sRGB for BOTH input and output.** Other color pipelines must convert into that space before applying the LUT. LUTs do not include RAW calibration, exposure compensation, highlight compression or grain, so applying the LUT to an arbitrary file in another application will not reproduce the entire renderer. Grain and color strength controls can be changed separately.

## Editing a film look

Look definitions live in [`raw2film/profiles/`](raw2film/profiles/) as YAML data files. Key parameters:

- `tone_points`: monotonic control points `[input_luma, output_luma]` in nonlinear sRGB, spanning 0–1. Interpolated by PCHIP.
- `saturation`: global color scaling in an RGB-luma/chroma approximation.
- `color_matrix`: a 3x3 RGB color mixing matrix.
- `hue_bands`: hue ranges with configurable hue shift and saturation changes. Hue angles are degrees; `width` defines a soft Gaussian range.
- `shadow_tint`, `highlight_tint`: small RGB offsets, strongest toward dark/bright extremes.
- `grain`: default effective standard deviation of grain, roughly in normalized display values.

Change a YAML file, rerun `raw2film compare`, and review the entire gallery. The CLI process reloads profile files when invoked again. Profiles are intentionally basic and manually tuned; no training pipeline yet.

## Reference-photo shortlist

[`references/manifest.yaml`](references/manifest.yaml) provides **12 research slots** (3 subjects per look) with source-page URLs. **No copyrighted image bytes are bundled.** The slots are **not finalized image selections**: `photo_url: null` and `rights: unknown` are deliberate. Before using any individual reference for training or distribution, document the actual photo, photographer, scanning or camera processing details, and permissions.

- Portra 400: portraits, foliage, architecture.
- Gold 200: sun, portraits, architecture.
- Classic Chrome: buildings, landscape, portraits.
- Classic Negative: street, foliage, portraits.

Film scans include scanner and lab choices, so an appearance seen on a website is not solely the film stock. Fujifilm's camera film simulations are digital renderings, not necessarily physical film stocks. Without *matched* target/input photographs, the initial color profiles can only be visually approximated; references don't provide a defensible per-pixel error measure.

## Limitations and next steps

- The RAW path uses the documented [rawpy linear output API](https://github.com/letmaik/rawpy/blob/main/README.md). **Real ARW decoding must be tested on an actual Sony file on a machine with rawpy installed**; development here verified the CLI and color engine using synthetic PNG inputs because network-installing rawpy was unavailable.
- 16-bit precision is preserved through RAW decode and float32 processing, but JPEG exports are 8-bit. Add 16-bit TIFF in a later release.
- The LUT works on gamma-encoded sRGB and cannot capture scene-linear or spectral cross-channel effects, film development chemistry, halation, film-specific grain distributions, scanner nonuniformity or sophisticated gamut mapping.
- `rawpy` converts/clips camera-native values to linear sRGB before film simulation. A future higher-quality pipeline could use camera DCP/ICC profiles and a wide-gamut floating-point intermediate such as linear Rec.2020 or ACEScg.
- Pure-Python/scipy LUT processing prioritizes clarity over GPU speed; memory optimization and thumbnail caching are future work.
- The `demo` command creates a **synthetic color-test chart**, not an actual photographic reference.

## Files

```text
raw2film/       RAW/JPEG decoding, color math, film renderer, CLI, gallery, demo
raw2film/profiles/ Four editable YAML look profiles
references/    12-slot, provenance-aware reference candidate manifest
tests/         Color and end-to-end CLI regression tests
```

## Verification

`pytest -q` runs the color math, LUT behavior, deterministic grain, neutral render, JPEG output, batch workflow, and gallery generation on synthetic test inputs. To do a real camera acceptance test after local installation:

```sh
raw2film compare /path/to/sony-photo.ARW --output ./arw-check
```

Check camera white balance, highlight retention, green foliage, skin tones, orientation, and that the neutral render is sensibly exposed. Compare output to a Lightroom neutral development as a sanity check, not a pixel-exact expectation.
