import numpy as np
import pytest
from raw2film.color import (srgb_decode, srgb_encode, highlight_compress,
                           rgb_to_hsv, hsv_to_rgb, load_profile, create_lut,
                           apply_lut, film_transform, export_cube,
                           compress_gamut, LUMA)


def test_srgb_roundtrip():
    x = np.linspace(0, 1, 101, dtype=np.float32)
    np.testing.assert_allclose(srgb_decode(srgb_encode(x)), x, atol=1e-6)


def test_hsv_roundtrip():
    rng = np.random.default_rng(4)
    x = rng.random((300, 3), dtype=np.float32)
    np.testing.assert_allclose(hsv_to_rgb(rgb_to_hsv(x)), x, atol=2e-6)


def test_highlight_knee():
    x = np.array([0, .3, .82, 1, 4], dtype=np.float32)
    y = highlight_compress(x)
    np.testing.assert_allclose(y[:3], x[:3], atol=1e-6)
    assert 0.82 < y[3] < 1 and y[-1] > y[3] and y[-1] <= 1


@pytest.mark.parametrize('name', ['portra400','gold200','classic_chrome','classic_negative'])
def test_profile_output_is_bounded_and_nontrivial(name):
    p = load_profile(name)
    test_rgb = np.array([[0.5, 0.5, 0.5], [0.2, .6, .2], [.8, .3, .18]], np.float32)
    processed = film_transform(test_rgb, p)
    assert np.all((processed >= 0) & (processed <= 1))
    assert not np.allclose(processed, test_rgb, atol=1e-3)
    lut = create_lut(p, 17)
    assert lut.shape == (17, 17, 17, 3)
    assert np.all(np.isfinite(lut))
    np.testing.assert_allclose(apply_lut(test_rgb, lut), processed, atol=.02)


def test_identity_lut():
    axis = np.linspace(0, 1, 17, dtype=np.float32)
    lut = np.stack(np.meshgrid(axis, axis, axis, indexing='ij'), -1)
    rng = np.random.default_rng(5)
    im = rng.random((19, 23, 3), dtype=np.float32)
    np.testing.assert_allclose(apply_lut(im, lut, chunk=39), im, atol=1e-6)


def test_cube_file(tmp_path):
    out = export_cube(load_profile('portra400'), tmp_path/'portra.cube', 9)
    lines = out.read_text().splitlines()
    assert 'LUT_3D_SIZE 9' in lines
    assert len(lines) == 4 + 9**3
    assert len(lines[-1].split()) == 3


def test_cube_red_axis_changes_fastest(tmp_path):
    identity = {'name': 'Identity', 'tone_points': [[0, 0], [.5, .5], [1, 1]]}
    out = export_cube(identity, tmp_path / 'identity.cube', 2)
    values = np.loadtxt(out, skiprows=4)
    np.testing.assert_allclose(values, [
        [0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0],
        [0, 0, 1], [1, 0, 1], [0, 1, 1], [1, 1, 1],
    ], atol=1e-6)


@pytest.mark.parametrize('knee', [0, 1, -0.1, 1.1, float('nan')])
def test_gamut_compression_rejects_invalid_knee(knee):
    with pytest.raises(ValueError, match='knee'):
        compress_gamut(np.array([[.2, .5, .8]], np.float32), knee=knee)


def test_gamut_compression_leaves_low_chroma_and_neutrals_unchanged():
    rgb = np.array([[0, 0, 0], [.2, .3, .4], [.7, .6, .5], [1, 1, 1]], np.float32)
    np.testing.assert_allclose(compress_gamut(rgb), rgb, atol=1e-7)


def test_gamut_compression_preserves_in_range_luma_and_color_direction():
    # Some channels lie outside the display gamut, but each pixel's luma is
    # representable. Compression must move toward gray, not rotate its color.
    rgb = np.array([[1.2, .35, .1], [-.1, .5, 1.1], [.95, .2, .9]], np.float32)
    luma = rgb @ LUMA
    result = compress_gamut(rgb)
    np.testing.assert_allclose(result @ LUMA, luma, atol=1e-7)
    before = rgb - luma[:, None]
    after = result - luma[:, None]
    np.testing.assert_allclose(np.cross(before, after), 0, atol=1e-7)
    assert np.all(np.sum(before * after, axis=-1) > 0)
    assert np.all(np.linalg.norm(after, axis=-1) < np.linalg.norm(before, axis=-1))
    assert np.all((result > 0) & (result < 1))


def test_gamut_compression_is_finite_and_bounded_for_out_of_gamut_values():
    rgb = np.random.default_rng(32).uniform(-2, 3, (13, 17, 3)).astype(np.float32)
    result = compress_gamut(rgb)
    assert result.shape == rgb.shape
    assert result.dtype == np.float32
    assert np.all(np.isfinite(result))
    assert np.all((result >= 0) & (result <= 1))


@pytest.mark.parametrize('name', ['portra400', 'gold200', 'classic_chrome', 'classic_negative'])
def test_profile_neutral_ramp_has_neutral_endpoints_and_no_highlight_plateau(name):
    ramp = np.repeat(np.linspace(0, 1, 1001, dtype=np.float32)[:, None], 3, axis=1)
    profile = load_profile(name)
    result = film_transform(ramp, profile)
    np.testing.assert_allclose(result[0], profile['tone_points'][0][1], atol=1e-7)
    np.testing.assert_allclose(result[-1], profile['tone_points'][-1][1], atol=2e-7)
    # A cast or a cap on one channel can make pale neutrals lose highlight
    # detail even when the overall luminance still appears to increase.
    assert np.all(np.diff(result, axis=0) > 0)
    assert np.all(result < 1)


def test_neutral_endpoints_preserves_tint_inside_the_tonal_range():
    profile = {'name': 'Tint test', 'tone_points': [[0, 0], [.5, .5], [1, 1]],
               'shadow_tint': [.01, 0, -.01], 'highlight_tint': [-.01, 0, .01],
               'neutral_endpoints': True, 'gamut_compression': True}
    rgb = np.repeat(np.array([0, .2, .5, .8, 1], np.float32)[:, None], 3, axis=1)
    result = film_transform(rgb, profile)
    np.testing.assert_allclose(result[[0, 2, 4]], rgb[[0, 2, 4]], atol=1e-7)
    assert result[1, 0] > result[1, 1] > result[1, 2]
    assert result[3, 0] < result[3, 1] < result[3, 2]
