import numpy as np
import pytest

from raw2film.render import develop, mix_look


def test_amplification_preserves_color_direction_at_gamut_edge():
    baseline = np.array([[[.8, .5, .3]]], dtype=np.float32)
    styled = np.array([[[.9, .55, .25]]], dtype=np.float32)
    result = mix_look(baseline, styled, 3)
    # Every channel shares one amplification amount, which approaches the
    # limiting red boundary without making a flat clipped region.
    amplification = (result-baseline) / (styled-baseline)
    np.testing.assert_allclose(amplification, np.full_like(amplification, amplification[0, 0, 0]), atol=1e-6)
    assert 1 < amplification[0, 0, 0] < 2
    assert np.all((result > 0) & (result < 1))


def test_strength_preserves_zero_and_one_endpoints():
    baseline = np.array([[[0, .4, 1], [.8, .6, .3]]], np.float32)
    styled = np.array([[[.1, .3, .9], [.7, .65, .4]]], np.float32)
    np.testing.assert_allclose(mix_look(baseline, styled, 0), baseline, atol=1e-7)
    np.testing.assert_allclose(mix_look(baseline, styled, 1), styled, atol=1e-7)


def test_amplification_has_smooth_onset_and_nearly_linear_small_displacements():
    baseline = np.array([[[.4, .5, .6]]], np.float32)
    styled = baseline + np.array([[[.001, -.002, .003]]], np.float32)
    delta = styled-baseline
    step = .01
    right_slope = (mix_look(baseline, styled, 1+step)-styled) / step
    np.testing.assert_allclose(right_slope, delta, rtol=.003, atol=1e-6)
    np.testing.assert_allclose(mix_look(baseline, styled, 3), baseline+3*delta, atol=1e-4)


def test_amplification_keeps_near_boundary_pixels_distinct():
    baseline = np.full((1, 2, 3), .2, np.float32)
    styled = np.array([[[.002, .1, .3], [.005, .1, .3]]], np.float32)
    medium = mix_look(baseline, styled, 2)
    strong = mix_look(baseline, styled, 3)
    assert np.all(strong[..., 0] > 0)
    assert np.all(strong[..., 0] < medium[..., 0])
    assert strong[0, 0, 0] < strong[0, 1, 0]


@pytest.mark.parametrize('look', ['portra400', 'gold200', 'classic_chrome', 'classic_negative'])
def test_strength_zero_normal_and_amplified(look):
    image = np.random.default_rng(8).uniform(.02, .5, (20, 24, 3)).astype(np.float32)
    neutral = develop(image, film='neutral')
    zero = develop(image, film=look, strength=0)
    normal = develop(image, film=look, strength=1, grain=False)
    strong = develop(image, film=look, strength=3, grain=False)
    np.testing.assert_allclose(zero, neutral, atol=1e-7)
    assert np.isfinite(strong).all() and strong.min() >= 0 and strong.max() <= 1
    assert np.mean(np.abs(strong-neutral)) > 1.5 * np.mean(np.abs(normal-neutral))


@pytest.mark.parametrize('strength', [-.1, 3.1, float('nan'), float('inf')])
def test_invalid_strength(strength):
    with pytest.raises(ValueError, match='strength'):
        develop(np.ones((2, 2, 3), dtype=np.float32), strength=strength)


def test_amplification_of_identical_pixels_is_finite():
    image = np.array([[[0, 0, 0], [.5, .5, .5], [1, 1, 1]]], dtype=np.float32)
    np.testing.assert_array_equal(mix_look(image, image, 3), image)
