# raw2film v0.1

A minimal, **working Python command-line RAW developer with configurable photographic looks**. It renders Sony a7 III `.ARW` photographs (and other rawpy-supported camera RAW formats) with four procedural, editable film-inspired color looks:

- Kodak **Portra 400** (`portra400`)
- Kodak **Gold 200** (`gold200`)
- Fujifilm **Classic Chrome** (`classic_chrome`)
- Fujifilm **Classic Negative** (`classic_negative`)

Despite the project name, the engine is not restricted to film emulation: new looks can express any photographic color treatment. The CLI supports `--look` (with `--film` and `--stock` aliases).

These are **film-inspired artistic approximations**, qualitatively reviewed against credited manufacturer examples. They are not officially licensed, measured, or scientifically calibrated recreations of the named stocks/simulations. Color results depend on the RAW developer, camera and lighting. This software is not affiliated with Kodak or Fujifilm.

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

# Start the interactive local editor (http://127.0.0.1:8843):
raw2film serve --input-dir ~/Documents

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

## Interactive editor

`raw2film serve` starts a local editor at **http://127.0.0.1:8843**.
Choose a photo from the optional `--input-dir` folder, or load a RAW through the
file picker/drop zone. Processing stays on your computer. The server binds only
to loopback; it is a local desktop companion, not a public hosting service.

- **Look strength, 0–300%:** 0% is neutral, 100% is the current profile, and
  higher values amplify its tonal and color changes. Above 100%, a smooth
  shoulder approaches the RGB gamut boundary while preserving the direction
  of each pixel's color change.
  It exaggerates the artistic treatment; it does not improve film accuracy.
- **Exposure, −3 to +3 EV:** affects both neutral and styled previews equally,
  so a brightness adjustment cannot masquerade as a stronger look.
- **Grain:** a separate multiplier for the selected profile. Above 100% look
  strength, increasing color strength does not also increase grain. The Fuji
  profiles have no default grain, so their grain multiplier has no effect.
- **Comparison:** inspect the neutral and styled rendering before exporting.
- **Export:** download a full-resolution sRGB JPEG with the current settings.
  Preview processing uses a 1400-pixel long edge for responsiveness. Grain is
  sized in output pixels, so its apparent size differs in a full-size export.

Private RAW files and rendered derivatives belong outside version control. The
repository ignores camera RAW formats, common photo-output formats and local
working/output folders; do not force-add private images.

The original files are never edited. Uploaded copies are temporary and removed
when the server shuts down normally. Keep this terminal running while editing;
press Ctrl-C to stop. Use `--port` to choose a different local port.

### CLI options

```sh
raw2film render path/to/photo.ARW --look portra400 --exposure +0.3
raw2film render photo.ARW --look gold200 --auto-exposure --strength 0.8
raw2film render photo.ARW --look gold200 --no-grain
raw2film render photo.ARW --look classic_chrome --strength 2.0
raw2film render photo.ARW --look portra400 --grain-multiplier 1.5 --seed 42
raw2film compare photo.ARW --exposure -0.3 --max-edge 1600
raw2film batch ./raws --look classic_negative --max-edge 2500
```

`--auto-exposure` uses a simple median-luminance estimate, capped at +/-2 stops. It is deliberately **off by default** because night scenes and high-key subjects fool simple metering; the default is the camera exposure with no arbitrary auto-brightening. Camera white balance is used by default for RAW files. Grain is deterministic for a given input, profile, and seed.

Comparison galleries record the effective exposure, strength, grain settings,
seed and output dimensions. Click an image to inspect the exported JPEG.
Rendering refuses to overwrite an input file, including through a symlink or
hardlink. Batch and comparison commands check all destinations before writing;
a RAW/JPEG pair with the same filename stem must be rendered separately or renamed
because it would otherwise produce the same output filename.

## Processing pipeline

1. **Decode RAW**: `rawpy`/LibRaw demosaics and applies camera WB and camera-to-sRGB color conversion, returning 16-bit **linear-light sRGB** (no rawpy auto-brightening, `gamma=(1,1)`). Standard JPEG/PNG inputs are treated as display-sRGB and decoded to linear-light first; embedded ICC profiles are converted when possible.
2. **Linear exposure**: multiply pixels by `2 ** EV`; optionally auto-meter the scene.
3. **Output shoulder**: a smooth highlight compression above a linear-light knee. This is a simple output transform, **not** full HDR reconstruction or actual chemical film response. Some highlight information may already be clipped by LibRaw.
4. **Color encode**: convert linear sRGB to standard nonlinear sRGB transfer curve.
5. **Film LUT**: apply a 33x33x33 3D LUT, generated from the YAML profile. The LUT contains a monotonic PCHIP luminance curve, chroma adjustment, 3x3 color matrix, selective hue/saturation operations, and luminance-weighted shadow/highlight tints. The bundled profiles also fade tint at neutral endpoints and softly compress chroma near the output gamut boundary.
6. **Finishing**: add subtle monochromatic, spatially correlated, luminance-dependent grain as configured. Fujifilm looks have grain disabled by default.
7. **Export**: write JPEG with an embedded sRGB ICC profile, leaving the original untouched.

**The `.cube` LUT uses display-referred, gamma-encoded sRGB for BOTH input and output.** Other color pipelines must convert into that space before applying the LUT. LUTs do not include RAW calibration, exposure compensation, highlight compression or grain, so applying the LUT to an arbitrary file in another application will not reproduce the entire renderer. Grain and color strength controls can be changed separately.

## Editing a film look

Look definitions live in [`raw2film/profiles/`](raw2film/profiles/) as YAML data files. Key parameters:

- `tone_points`: monotonic control points `[input_luma, output_luma]` in nonlinear sRGB, spanning 0–1. Interpolated by PCHIP.
- `saturation`: global color scaling in an RGB-luma/chroma approximation.
- `color_matrix`: a 3x3 RGB color mixing matrix.
- `hue_bands`: hue ranges with configurable hue shift and saturation changes. Hue angles are degrees; `width` defines a soft Gaussian range.
- `shadow_tint`, `highlight_tint`: small RGB offsets weighted toward shadows/highlights.
- `neutral_endpoints`: fade those tints near black and white; enabled in bundled profiles.
- `gamut_compression`: softly compress chroma near the sRGB boundary; enabled in bundled profiles.
- `grain`: default effective standard deviation of grain, roughly in normalized display values.

Change a YAML file, rerun `raw2film compare`, and review the entire gallery. The CLI process reloads profile files when invoked again. Profiles are intentionally basic and manually tuned; no training pipeline yet.

## Reference review

[`references/manifest.yaml`](references/manifest.yaml) records inspected Kodak and
Fujifilm examples with publisher links and photographer credits.
[`references/REVIEW.md`](references/REVIEW.md) explains the resulting profile
changes and remaining limits. No copyrighted references, private RAW files or
private rendered derivatives are bundled in the repository.

This is a qualitative review across different photographs. Without matched input
and target photographs, references cannot establish a per-pixel accuracy score.
Film scans also reflect scanner, lab and editing choices. The numeric profile
parameters remain subjective, and skin-tone and grain fidelity are unvalidated.
Classic Negative's brightness-dependent, per-color contrast is not fully modeled.

## Limitations and next steps

- The RAW path uses the documented [rawpy linear output API](https://github.com/letmaik/rawpy/blob/main/README.md). Local acceptance testing exercises Sony ARW decoding, all looks, embedded sRGB ICC profiles and source preservation. This verifies rendering behavior, not accuracy for every camera or lighting condition.
- 16-bit precision is preserved through RAW decode and float32 processing, but JPEG exports are 8-bit. Add 16-bit TIFF in a later release.
- The LUT works on gamma-encoded sRGB and cannot capture scene-linear or spectral cross-channel effects, film development chemistry, halation, film-specific grain distributions, scanner nonuniformity or a perceptually calibrated gamut transform.
- `rawpy` converts/clips camera-native values to linear sRGB before film simulation. A future higher-quality pipeline could use camera DCP/ICC profiles and a wide-gamut floating-point intermediate such as linear Rec.2020 or ACEScg.
- Pure-Python/scipy LUT processing prioritizes clarity over GPU speed; memory optimization and thumbnail caching are future work.
- The `demo` command creates a **synthetic color-test chart**, not an actual photographic reference.

## Files

```text
raw2film/       RAW/JPEG decoding, color math, film renderer, CLI, gallery, demo
raw2film/profiles/ Four editable YAML look profiles
references/    Reviewed source manifest, credits and qualitative findings
tests/         Color and end-to-end CLI regression tests
```

## Verification

`pytest -q` runs the color math, LUT behavior, deterministic grain, neutral render, JPEG output, batch workflow, and gallery generation on synthetic test inputs. To do a real camera acceptance test after local installation:

```sh
raw2film compare /path/to/sony-photo.ARW --output ./arw-check
```

Check camera white balance, highlight retention, green foliage, skin tones, orientation, and that the neutral render is sensibly exposed. Compare output to a Lightroom neutral development as a sanity check, not a pixel-exact expectation.

An optional integration test exercises real RAW decoding, all five JPEG outputs,
ICC embedding and source preservation without committing a private photograph:

```sh
RAW2FILM_TEST_RAW=/path/to/sony-photo.ARW pytest -q
```

Real-camera test inputs and rendered outputs remain local and untracked. Pixel
clipping statistics describe exported RGB values, not sensor clipping or film
accuracy. Grain is currently sized in output pixels, so its apparent size varies
with export resolution.
