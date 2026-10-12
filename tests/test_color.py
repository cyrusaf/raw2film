import numpy as np
import pytest
from raw2film.color import (srgb_decode, srgb_encode, highlight_compress,
                           rgb_to_hsv, hsv_to_rgb, load_profile, create_lut,
                           apply_lut, film_transform, export_cube)


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
