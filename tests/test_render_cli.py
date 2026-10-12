from pathlib import Path
import numpy as np
from PIL import Image
from raw2film.cli import main
from raw2film.gallery import FILMS
from raw2film.io import load_linear_rgb
from raw2film.render import develop, apply_grain


def create_test_image(tmp_path):
    im = np.arange(24*32*3, dtype=np.uint16).reshape(24,32,3) % 256
    filename = tmp_path/'test.png'
    Image.fromarray(im.astype(np.uint8), 'RGB').save(filename)
    return filename


def test_render_and_compare(tmp_path):
    original = create_test_image(tmp_path)
    assert main(['render', str(original), '--film', 'gold200', '--output', str(tmp_path/'gold.jpg'), '--no-grain']) == 0
    assert (tmp_path/'gold.jpg').exists()
    assert main(['compare', str(original), '--output', str(tmp_path/'gallery'), '--no-grain']) == 0
    assert (tmp_path/'gallery'/'index.html').exists()
    for film in FILMS:
        assert (tmp_path/'gallery'/f'{film}.jpg').exists()


def test_neutral_and_strength(tmp_path):
    inp = load_linear_rgb(create_test_image(tmp_path))
    base = develop(inp, film='neutral')
    zero = develop(inp, film='gold200', strength=0.0)
    np.testing.assert_allclose(base, zero, atol=1e-7)
    nonzero = develop(inp, film='gold200', grain=False)
    assert not np.allclose(base, nonzero, atol=0.005)


def test_seed_is_reproducible():
    image = np.full((20, 30, 3), .5, np.float32)
    a = apply_grain(image, .025, 2)
    b = apply_grain(image, .025, 2)
    c = apply_grain(image, .025, 3)
    np.testing.assert_array_equal(a,b)
    assert not np.array_equal(a,c)


def test_cli_export(tmp_path):
    assert main(['export-lut', '--film', 'classic_chrome', '--size', '9',
                 '--output', str(tmp_path/'chrome.cube')]) == 0
    assert (tmp_path/'chrome.cube').stat().st_size > 10000


def test_bad_film_and_missing_file(tmp_path):
    assert main(['render', str(tmp_path/'absent.ARW')]) == 2


def test_batch(tmp_path):
    src = tmp_path / 'input'
    src.mkdir()
    create_test_image(src)
    assert main(['batch', str(src), '--film', 'portra400',
                 '--output', str(tmp_path/'out'), '--no-grain']) == 0
    assert (tmp_path/'out'/'test_portra400.jpg').exists()


def test_new_look_flag_and_stock_alias(tmp_path):
    original = create_test_image(tmp_path)
    assert main(['render', str(original), '--look', 'classic_negative',
                 '--output', str(tmp_path/'negative.jpg'), '--no-grain']) == 0
    assert main(['export-lut', '--stock', 'gold200', '--size', '3',
                 '--output', str(tmp_path/'gold.cube')]) == 0
    assert (tmp_path/'negative.jpg').exists()
    assert (tmp_path/'gold.cube').exists()
