"""Loopback-only RAW editor server. Photo processing stays on this computer."""
from __future__ import annotations

import base64
from collections import OrderedDict
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
import math
from pathlib import Path
import tempfile
import threading
import time
from urllib.parse import parse_qs, quote, urlsplit
import uuid

import numpy as np
from PIL import Image, ImageCms

from .io import RAW_EXTENSIONS, RGB_EXTENSIONS, load_linear_rgb
from .render import develop

MAX_UPLOAD = 150 * 1024 * 1024
LOOKS = {"neutral": "Neutral", "portra400": "Portra 400", "gold200": "Gold 200",
         "classic_chrome": "Classic Chrome", "classic_negative": "Classic Negative"}
SUPPORTED = RAW_EXTENSIONS | RGB_EXTENSIONS


class APIError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@dataclass
class Photo:
    path: Path
    name: str
    linear: np.ndarray
    width: int
    height: int
    uploaded: bool = False


def jpeg_bytes(rgb: np.ndarray) -> bytes:
    image = Image.fromarray(np.uint8(np.round(np.clip(rgb, 0, 1) * 255)), "RGB")
    target = BytesIO()
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    image.save(target, "JPEG", quality=94, subsampling=0, icc_profile=icc)
    return target.getvalue()


class Application:
    def __init__(self, input_dir: str | Path | None = None):
        self.input_dir = Path(input_dir).expanduser().resolve() if input_dir else None
        if self.input_dir is not None and not self.input_dir.is_dir():
            raise ValueError("Input directory does not exist")
        self.lock = threading.RLock()
        self._temporary = tempfile.TemporaryDirectory(prefix="raw2film-")
        self._library: dict[str, Path] = {}
        self.photos: OrderedDict[str, Photo] = OrderedDict()

    def close(self):
        with self.lock:
            self.photos.clear()
            self._temporary.cleanup()

    def library(self):
        with self.lock:
            previous = {path: key for key, path in self._library.items()}
            paths = [] if self.input_dir is None else sorted(
                (path for path in self.input_dir.iterdir()
                 if path.is_file() and not path.is_symlink() and path.suffix.lower() in SUPPORTED),
                key=lambda path: path.name.lower())
            self._library = {previous.get(path, uuid.uuid4().hex): path for path in paths}
            return {"images": [{"id": key, "name": path.name} for key, path in self._library.items()],
                    "looks": [{"id": key, "name": name} for key, name in LOOKS.items()]}

    def _check_source(self, photo: Photo):
        if not photo.path.is_file() or photo.path.is_symlink():
            raise APIError("The source image is no longer available", 404)
        root = Path(self._temporary.name) if photo.uploaded else self.input_dir
        if root is None or photo.path.resolve().parent != root.resolve():
            raise APIError("Source image is outside the configured folder", 403)

    def _load(self, path: Path, name: str, uploaded: bool = False):
        try:
            linear = load_linear_rgb(path, max_edge=1400)
            height, width = linear.shape[:2]
            # Read full dimensions from metadata without a second demosaic.
            if path.suffix.lower() in RAW_EXTENSIONS:
                import rawpy
                with rawpy.imread(str(path)) as raw:
                    width, height = raw.sizes.width, raw.sizes.height
                    if raw.sizes.flip in (5, 6):
                        width, height = height, width
            else:
                with Image.open(path) as image:
                    width, height = image.size
                    if image.getexif().get(274) in (5, 6, 7, 8):
                        width, height = height, width
        except Exception as exc:
            raise APIError("Could not decode this image. Check that it is a supported, valid photo.") from exc
        image_id = uuid.uuid4().hex
        self.photos[image_id] = Photo(path, name, linear, width, height, uploaded)
        while len(self.photos) > 3:
            _, expired = self.photos.popitem(last=False)
            if expired.uploaded:
                expired.path.unlink(missing_ok=True)
        return {"image_id": image_id, "name": name, "width": width, "height": height,
                "preview_width": linear.shape[1], "preview_height": linear.shape[0]}

    def load(self, image_id):
        with self.lock:
            if not isinstance(image_id, str) or image_id not in self._library:
                raise APIError("Unknown library image. Refresh the folder list.", 404)
            path = self._library[image_id]
            if path.is_symlink() or path.resolve().parent != self.input_dir:
                raise APIError("Image is outside the configured folder", 403)
            return self._load(path, path.name)

    def upload(self, name: str, body: bytes):
        with self.lock:
            name = Path(name.replace("\\", "/")).name
            if not name or Path(name).suffix.lower() not in SUPPORTED:
                raise APIError("Choose a supported RAW, JPEG, PNG, TIFF, or WebP image")
            if not body or len(body) > MAX_UPLOAD:
                raise APIError("Image must be between 1 byte and 150 MB", 413)
            path = Path(self._temporary.name) / (uuid.uuid4().hex + Path(name).suffix.lower())
            path.write_bytes(body)
            try:
                return self._load(path, name, uploaded=True)
            except Exception:
                path.unlink(missing_ok=True)
                raise

    def _settings(self, values):
        image_id = values.get("image_id")
        if not isinstance(image_id, str) or image_id not in self.photos:
            raise APIError("Image session expired. Open the photo again.", 404)
        look = values.get("look", "portra400")
        if not isinstance(look, str) or look not in LOOKS:
            raise APIError("Unknown film look")
        numeric = {}
        for key, default, low, high in (("strength", 1, 0, 3), ("exposure", 0, -3, 3), ("grain", 1, 0, 2)):
            try:
                if isinstance(values.get(key), bool):
                    raise ValueError()
                value = float(values.get(key, default))
                if not math.isfinite(value) or not low <= value <= high:
                    raise ValueError()
            except (ValueError, TypeError):
                raise APIError(f"{key.capitalize()} must be between {low} and {high}") from None
            numeric[key] = value
        self.photos.move_to_end(image_id)
        return self.photos[image_id], {"film": look, "strength": numeric["strength"],
            "exposure": numeric["exposure"], "grain": numeric["grain"] > 0,
            "grain_multiplier": numeric["grain"], "seed": 42}

    def preview(self, values):
        with self.lock:
            started = time.perf_counter()
            photo, settings = self._settings(values)
            neutral = develop(photo.linear, film="neutral", exposure=settings["exposure"], grain=False)
            styled = develop(photo.linear, **settings)
            # Encoded output saturation, including film/grain; not sensor clipping.
            clipping = float(np.mean(np.any((styled <= 0) | (styled >= 1), axis=-1)) * 100)
            def data_url(rgb):
                return "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes(rgb)).decode("ascii")
            return {"neutral": data_url(neutral), "styled": data_url(styled),
                    "width": styled.shape[1], "height": styled.shape[0],
                    "elapsed_ms": round((time.perf_counter() - started) * 1000), "clipping_pct": clipping}

    def export(self, values):
        with self.lock:
            photo, settings = self._settings(values)
            self._check_source(photo)
            try:
                linear = load_linear_rgb(photo.path)
            except Exception as exc:
                raise APIError("Could not read the original image for export") from exc
            output = jpeg_bytes(develop(linear, **settings))
            return output, f"{Path(photo.name).stem}_{settings['film']}.jpg"


def make_handler(app: Application):
    class Handler(BaseHTTPRequestHandler):
        # A finite socket timeout prevents stalled upload clients holding the render lock.
        timeout = 30

        def log_message(self, format, *args):
            pass  # Photo names/settings do not need to be logged.

        def _send(self, status, body, content_type="application/json", extra=None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data, status=200):
            self._send(status, json.dumps(data).encode())

        def _guard(self):
            host, port = self.server.server_address[:2]
            expected = f"{host}:{port}"
            if self.headers.get("Host") != expected:
                raise APIError("Use the editor's 127.0.0.1 address", 403)
            origin = self.headers.get("Origin")
            if origin is not None and origin != f"http://{expected}":
                raise APIError("Requests from other origins are not allowed", 403)
            if self.headers.get("Sec-Fetch-Site") == "cross-site":
                raise APIError("Cross-site requests are not allowed", 403)

        def _body(self, maximum):
            if self.headers.get("Transfer-Encoding"):
                raise APIError("Chunked uploads are not supported")
            try:
                size = int(self.headers.get("Content-Length", "-1"))
            except ValueError:
                raise APIError("A valid Content-Length is required", 411) from None
            if size < 0:
                raise APIError("Content-Length is required", 411)
            if size > maximum:
                raise APIError("Image exceeds the 150 MB limit" if maximum == MAX_UPLOAD else "Request is too large", 413)
            body = self.rfile.read(size)
            if len(body) != size:
                raise APIError("Upload was incomplete")
            return body

        def _handle(self):
            try:
                self._guard()
                parsed = urlsplit(self.path)
                query = {key: value[-1] for key, value in parse_qs(parsed.query).items()}
                if self.command == "GET":
                    if parsed.path == "/api/library":
                        self._json(app.library())
                    elif parsed.path == "/api/export":
                        body, name = app.export(query)
                        self._send(200, body, "image/jpeg", {"Content-Disposition": f"attachment; filename=raw2film.jpg; filename*=UTF-8''{quote(name, safe='')}"})
                    elif parsed.path in ("/", "/index.html", "/style.css", "/app.js"):
                        filename = {"/": "index.html", "/index.html": "index.html", "/style.css": "style.css", "/app.js": "app.js"}[parsed.path]
                        mime = {"index.html": "text/html; charset=utf-8", "style.css": "text/css; charset=utf-8", "app.js": "text/javascript; charset=utf-8"}[filename]
                        self._send(200, (Path(__file__).parent / "web" / filename).read_bytes(), mime)
                    else:
                        raise APIError("Not found", 404)
                elif self.command == "POST":
                    # Bound both upload buffering and rendering to one request at a time.
                    with app.lock:
                        if parsed.path == "/api/upload":
                            result = app.upload(query.get("name", ""), self._body(MAX_UPLOAD))
                        elif parsed.path in ("/api/load", "/api/preview"):
                            try:
                                values = json.loads(self._body(16384))
                            except (ValueError, UnicodeDecodeError):
                                raise APIError("Request must contain valid JSON") from None
                            if not isinstance(values, dict):
                                raise APIError("Request must contain a JSON object")
                            result = app.load(values.get("id")) if parsed.path == "/api/load" else app.preview(values)
                        else:
                            raise APIError("Not found", 404)
                    self._json(result)
                else:
                    raise APIError("Method not allowed", 405)
            except APIError as exc:
                self._json({"error": str(exc)}, exc.status)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                self._json({"error": "The request could not be completed. Try opening the image again."}, 500)

        do_GET = _handle
        do_POST = _handle
        do_OPTIONS = _handle
    return Handler


def run_server(input_dir: str | Path | None = None, port: int = 8843):
    app = Application(input_dir)
    try:
        with ThreadingHTTPServer(("127.0.0.1", port), make_handler(app)) as server:
            server.daemon_threads = True
            print(f"RAW editor: http://127.0.0.1:{server.server_port}/", flush=True)
            print("Photos stay local. Press Ctrl-C to stop.", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
    finally:
        app.close()
