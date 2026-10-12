import os

from PIL import Image
import pytest

from raw2film.cli import main
from raw2film.gallery import make_gallery
from raw2film.render import render_file


def save_image(path):
    Image.new("RGB", (8, 6), (80, 130, 180)).save(path)
    return path.read_bytes()


@pytest.mark.parametrize("alias", ["same", "symlink", "hardlink"])
def test_render_preserves_source_when_output_aliases_input(tmp_path, alias):
    source = tmp_path / "original.png"
    original = save_image(source)
    destination = source
    if alias != "same":
        destination = tmp_path / "output.jpg"
        if alias == "symlink":
            destination.symlink_to(source)
        else:
            os.link(source, destination)

    with pytest.raises(ValueError, match="overwrite an input file"):
        render_file(source, destination, "gold200")

    assert source.read_bytes() == original


def test_render_rejects_raw_source_overwrite_before_decoding(tmp_path):
    source = tmp_path / "original.ARW"
    original = b"RAW source must never be replaced with JPEG bytes"
    source.write_bytes(original)

    assert main(["render", str(source), "--output", str(source)]) == 2
    assert source.read_bytes() == original


def test_compare_preflights_all_outputs_before_writing(tmp_path):
    source = tmp_path / "gold200.jpg"
    original = save_image(source)

    with pytest.raises(ValueError, match="overwrite an input file"):
        make_gallery(source, tmp_path)

    assert source.read_bytes() == original
    assert set(tmp_path.iterdir()) == {source}


def test_batch_rejects_duplicate_stems_before_any_output(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    save_image(inputs / "a.png")
    save_image(inputs / "photo.jpg")
    # A RAW+JPEG pair is a normal camera import. It must not lose one rendering.
    (inputs / "photo.ARW").write_bytes(b"placeholder RAW")
    originals = {path: path.read_bytes() for path in inputs.iterdir()}
    output = tmp_path / "rendered"

    assert main(["batch", str(inputs), "--output", str(output)]) == 2

    assert not output.exists()
    assert all(path.read_bytes() == data for path, data in originals.items())


def test_batch_rejects_overwrite_of_another_input_before_any_output(tmp_path):
    save_image(tmp_path / "a.png")
    save_image(tmp_path / "photo.png")
    save_image(tmp_path / "photo_gold200.jpg")
    originals = {path: path.read_bytes() for path in tmp_path.iterdir()}

    assert main(["batch", str(tmp_path), "--look", "gold200",
                 "--output", str(tmp_path)]) == 2

    assert set(tmp_path.iterdir()) == set(originals)
    assert all(path.read_bytes() == data for path, data in originals.items())
