import numpy as np
import pytest

from raw2film.render import develop, mix_look


def test_amplification_preserves_color_direction_at_gamut_edge():
    baseline = np.array([[[.8, .5, .3]]], dtype=np.float32)
    styled = np.array([[[.9, .55, .25]]], dtype=np.float32)
    result = mix_look(baseline, styled, 3)
    # Red reaches its boundary at 2x, so every channel must stop at 2x.
    np.testing.assert_allclose(result, [[[1, .6, .2]]], atol=1e-6)


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
