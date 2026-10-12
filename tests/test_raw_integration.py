"""Optional real-camera acceptance test; private photographs stay outside Git.

Run with RAW2FILM_TEST_RAW=/path/to/photo.ARW pytest -q.
"""
import hashlib
import os
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

from raw2film.gallery import FILMS, make_gallery
from raw2film.io import load_linear_rgb


@pytest.mark.skipif(not os.environ.get('RAW2FILM_TEST_RAW'),
                    reason='Set RAW2FILM_TEST_RAW to a local camera RAW')
def test_real_raw_comparison(tmp_path):
    source = Path(os.environ['RAW2FILM_TEST_RAW'])
    before = hashlib.sha256(source.read_bytes()).digest()
    linear = load_linear_rgb(source, max_edge=800)
    assert linear.dtype == np.float32
    assert linear.shape[-1] == 3 and max(linear.shape[:2]) == 800
    assert np.isfinite(linear).all()
    assert linear.max() > linear.min()
    assert 0 <= linear.min() <= linear.max() <= 1
    page = make_gallery(source, tmp_path / 'gallery', exposure=1, max_edge=800)
    assert 'Exposure: +1.00 EV' in page.read_text()
    decoded = []
    for film in FILMS:
        with Image.open(page.parent / f'{film}.jpg') as im:
            assert im.info.get('icc_profile')
            assert im.size == (linear.shape[1], linear.shape[0])
            decoded.append(np.asarray(im).copy())
    for rendered in decoded[1:]:
        assert not np.array_equal(rendered, decoded[0])
    assert hashlib.sha256(source.read_bytes()).digest() == before
