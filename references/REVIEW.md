# Reference review — 2026-10-12

The four profiles were reviewed against the credited manufacturer examples in
[manifest.yaml](manifest.yaml). This is a qualitative comparison across different
photographs, not matched calibration. All numerical profile settings remain
subjective. The repository contains source links and credits, not photographs.

| Look | Observed reference direction | Adjustment |
| --- | --- | --- |
| Portra 400 | Kodak's examples combine lively color, deep shadows and relatively natural pale surfaces; they do not support a uniformly faded pastel treatment. | Reduced black lift and green suppression; restored some saturation and restrained split toning. |
| Gold 200 | Warm light and vivid reds coexist with blue skies and nearly neutral bright surfaces. | Kept its colorful treatment while reducing the yellow highlight bias. |
| Classic Chrome | Fujifilm's examples show restrained colors, cool shadows and mostly neutral highlights. Blue skies are not uniformly teal. | Reduced the blue-to-cyan shift, strengthened shadow contrast and added selective magenta suppression. |
| Classic Negative | Fujifilm's examples retain blue skies, strong reds and firm blacks. A universal magenta highlight cast is not evident. | Reduced broad hue shifts, strengthened shadow contrast and replaced the strong magenta highlight tint with restrained warmth. |

Across all four profiles, highlight/shadow tint now fades at neutral endpoints.
A soft chroma compression reduces abrupt channel clipping near the sRGB boundary.
Above 100% strength, a smooth shoulder also limits amplification without a hard
channel plateau. These are output-rendering choices, not measurements of film
chemistry.

## Sources and interpretation

Kodak's [catalogue](https://kodakprofessional.com/sites/default/files/files/resources/Kodak%20Catalogue%20-%20Final%20-%20High%20Res%20%28Print%29.pdf),
PDF pages 5 and 7, supplies the inspected Portra and Gold examples and photographer
credits. Lighting, film development, scanning and editing can all influence their
appearance. The Soomin Yim Gold image also uses flash.

Fujifilm's [Classic Chrome](https://www.fujifilm-x.com/global/products/film-simulation/classic-chrome/)
and [Classic Negative](https://www.fujifilm-x.com/global/products/film-simulation/classic-neg/)
galleries supply the inspected simulation examples. Their camera settings, white
balance and subsequent processing are not specified. Fujifilm describes Chrome
as an imagined documentary-film treatment, rather than a named physical stock.
Its [Classic Negative design account](https://www.fujifilm-x.com/en-my/stories/x-pro3-stories-2-learning-from-film/)
describes SUPERIA inspiration and brightness-dependent, per-color contrast.
The present global curve, hue bands and tints do **not** fully model that behavior.

Kodak's [Portra technical publication](https://kodakprofessional.com/sites/default/files/2025-07/e4050.pdf)
and [Gold technical publication](https://www.kodakprofessional.com/sites/default/files/wysiwyg/pro/resources/E7022_Gold_200.pdf)
report Print Grain Index values of 37 and 44 respectively for 35 mm film enlarged
to a 4 × 6 inch print. This supports only the direction of Gold having more visible
grain under those conditions. It does not calibrate the renderer's grain amount,
size or spatial distribution; those settings were retained.

## What this review cannot establish

- No matched camera RAW / film scan or camera RAW / Fujifilm JPEG pairs were used,
  so there is no defensible numerical film-match score.
- Skin-tone fidelity and film-specific grain remain unvalidated.
- Exposure and white balance substantially change the result. A stronger setting
  amplifies the treatment; it is not a higher-accuracy setting.
- Film scans reflect the lab and scanner as well as the stock. These profiles
  offer a coherent interpretation, not a unique or officially approved rendering.

A future calibration should use matched scenes, controlled exposure and white
balance, recorded camera/scan settings, and reference images with appropriate
permission. Private test photographs and their rendered derivatives stay outside
version control.
