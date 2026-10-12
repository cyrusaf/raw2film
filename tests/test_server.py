"""Exercise the editor's actual HTTP boundary with tiny, local fixtures."""
import base64
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from io import BytesIO
import json
from pathlib import Path
import threading
from unittest.mock import patch
from urllib.parse import urlencode

import numpy as np
from PIL import Image
import pytest

from raw2film.server import Application, APIError, MAX_UPLOAD, make_handler


def png_bytes(width=31, height=19):
    pixels = np.zeros((height, width, 3), dtype=np.uint8)
    pixels[:] = (85, 140, 190)
    target = BytesIO()
    Image.fromarray(pixels).save(target, "PNG")
    return target.getvalue()


@pytest.fixture
def editor(tmp_path):
    (tmp_path / "photo.png").write_bytes(png_bytes())
    (tmp_path / "ignore.txt").write_text("not an image")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "hidden.png").write_bytes(png_bytes())
    (tmp_path / "linked.png").symlink_to(nested / "hidden.png")
    app = Application(tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield app, server
    server.shutdown()
    server.server_close()
    thread.join()
    app.close()


def request(editor, method, path, data=None, headers=None):
    _, server = editor
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    body = json.dumps(data).encode() if isinstance(data, dict) else data
    connection.request(method, path, body=body, headers=headers or {})
    response = connection.getresponse()
    content = response.read()
    result = (response.status, dict(response.getheaders()), content)
    connection.close()
    return result


def json_request(editor, method, path, data=None, headers=None):
    status, _, body = request(editor, method, path, data, headers)
    return status, json.loads(body)


def load_photo(editor):
    status, library = json_request(editor, "GET", "/api/library")
    assert status == 200
    status, photo = json_request(editor, "POST", "/api/load", {"id": library["images"][0]["id"]})
    assert status == 200
    return photo


def test_library_scope_and_preview_cached_decode(editor):
    app, _ = editor
    first = app.library()
    assert [entry["name"] for entry in first["images"]] == ["photo.png"]
    assert first == app.library()
    photo = load_photo(editor)
    assert (photo["width"], photo["height"]) == (31, 19)
    assert (photo["preview_width"], photo["preview_height"]) == (31, 19)
    with patch("raw2film.server.load_linear_rgb", side_effect=AssertionError("preview must reuse decoded pixels")):
        status, preview = json_request(editor, "POST", "/api/preview", {
            "image_id": photo["image_id"], "look": "portra400", "strength": 2.5, "grain": 0})
    assert status == 200
    for key in ("neutral", "styled"):
        image = Image.open(BytesIO(base64.b64decode(preview[key].split(",", 1)[1])))
        assert image.size == (31, 19)
        assert image.info["icc_profile"]
    assert preview["neutral"] != preview["styled"]
    assert 0 <= preview["clipping_pct"] <= 100


def test_zero_strength_equals_neutral_and_export_matches(editor):
    photo = load_photo(editor)
    settings = {"image_id": photo["image_id"], "look": "classic_negative", "strength": 0, "exposure": 0.75, "grain": 2}
    status, preview = json_request(editor, "POST", "/api/preview", settings)
    assert status == 200
    assert preview["neutral"] == preview["styled"]
    status, headers, exported = request(editor, "GET", "/api/export?" + urlencode(settings))
    assert status == 200
    assert headers["Content-Type"] == "image/jpeg"
    assert "attachment" in headers["Content-Disposition"]
    assert exported == base64.b64decode(preview["styled"].split(",", 1)[1])
    assert Image.open(BytesIO(exported)).info["icc_profile"]


def test_upload_and_session_eviction(editor):
    app, _ = editor
    photo = load_photo(editor)
    for index in range(3):
        status, uploaded = json_request(editor, "POST", f"/api/upload?name=new{index}.PNG", png_bytes(11, 7))
        assert status == 200
        assert uploaded["name"] == f"new{index}.PNG"
        assert uploaded["width"] == 11
    assert len(app.photos) == 3
    status, error = json_request(editor, "POST", "/api/preview", {"image_id": photo["image_id"]})
    assert status == 404
    assert "expired" in error["error"]
    temp = Path(app._temporary.name)
    assert len(list(temp.iterdir())) == 3
    app.close()
    assert not temp.exists()


def test_resize_preview_export_original_and_do_not_modify_source(editor):
    app, _ = editor
    source = app.input_dir / "large.png"
    original = png_bytes(1600, 100)
    source.write_bytes(original)
    library = app.library()
    selected = next(entry for entry in library["images"] if entry["name"] == "large.png")
    photo = app.load(selected["id"])
    assert photo["width"] == 1600
    assert photo["preview_width"] == 1400
    status, _, exported = request(editor, "GET", "/api/export?" + urlencode({"image_id": photo["image_id"], "look": "gold200", "strength": 2, "grain": 0}))
    assert status == 200
    assert Image.open(BytesIO(exported)).size == (1600, 100)
    assert source.read_bytes() == original


@pytest.mark.parametrize("field,value", [("strength", -0.1), ("strength", 3.1), ("strength", "nan"),
    ("exposure", "inf"), ("exposure", -4), ("grain", 2.1), ("grain", True), ("look", "../anything")])
def test_invalid_settings_preview_and_export(editor, field, value):
    photo = load_photo(editor)
    settings = {"image_id": photo["image_id"], field: value}
    assert json_request(editor, "POST", "/api/preview", settings)[0] == 400
    # Boolean URL query serializes to True and is rejected as nonnumeric.
    assert request(editor, "GET", "/api/export?" + urlencode(settings))[0] == 400


def test_invalid_files_json_and_identifiers(editor):
    assert json_request(editor, "POST", "/api/load", {"id": "/etc/passwd"})[0] == 404
    assert json_request(editor, "POST", "/api/preview", {"image_id": "missing"})[0] == 404
    assert json_request(editor, "POST", "/api/load", b"[")[0] == 400
    assert json_request(editor, "POST", "/api/load", b"[]")[0] == 400
    assert json_request(editor, "POST", "/api/upload?name=bad.png", b"not a png")[0] == 400
    assert json_request(editor, "POST", "/api/upload?name=bad.exe", b"not a photo")[0] == 400
    assert json_request(editor, "POST", "/api/upload?name=empty.png", b"")[0] == 413
    assert request(editor, "POST", "/api/upload?name=large.png", b"", {"Content-Length": str(MAX_UPLOAD + 1)})[0] == 413
    assert list(Path(editor[0]._temporary.name).iterdir()) == []


def test_origin_host_and_filesystem_guards(editor):
    assert request(editor, "GET", "/api/library", headers={"Origin": "https://evil.example"})[0] == 403
    assert request(editor, "POST", "/api/upload?name=photo.png", png_bytes(), {"Origin": "null"})[0] == 403
    assert request(editor, "GET", "/api/library", headers={"Host": "evil.example"})[0] == 403
    assert request(editor, "GET", "/api/library", headers={"Sec-Fetch-Site": "cross-site"})[0] == 403
    assert request(editor, "GET", "/../../etc/passwd")[0] == 404
    assert request(editor, "GET", "/api/library", headers={"Origin": f"http://127.0.0.1:{editor[1].server_port}"})[0] == 200
    assert request(editor, "OPTIONS", "/api/library")[0] == 405


def test_source_symlink_changed_after_library(editor):
    app, _ = editor
    library = app.library()
    path = app.input_dir / "photo.png"
    path.unlink()
    path.symlink_to(app.input_dir / "nested" / "hidden.png")
    with pytest.raises(APIError, match="outside"):
        app.load(library["images"][0]["id"])


def test_uploaded_export_resolves_temporary_directory_alias(editor, tmp_path):
    app, _ = editor
    # macOS commonly exposes the same temp directory through /var and /private/var.
    actual_temp = Path(app._temporary.name).resolve()
    alias = tmp_path / "temporary-alias"
    alias.symlink_to(actual_temp, target_is_directory=True)
    with patch.object(app._temporary, "name", str(alias)):
        photo = app.upload("upload.png", png_bytes(13, 9))
        status, _, body = request(editor, "GET", "/api/export?" + urlencode({
            "image_id": photo["image_id"], "look": "portra400", "grain": 0}))
        assert status == 200
        assert Image.open(BytesIO(body)).size == (13, 9)
        assert Image.open(BytesIO(body)).info["icc_profile"]
