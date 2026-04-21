#!/usr/bin/env python3
import os
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import uuid
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlencode, urlparse

from flask import Flask, jsonify, request, send_from_directory
from playwright.sync_api import sync_playwright

RENDER_HOST = os.environ.get("RENDER_HOST", "0.0.0.0")
RENDER_PORT = int(os.environ.get("RENDER_PORT", "5001"))
RENDER_PUBLIC_URL = os.environ.get("RENDER_PUBLIC_URL", f"http://127.0.0.1:{RENDER_PORT}").rstrip("/")
RENDER_TIMEOUT_SECONDS = int(os.environ.get("RENDER_TIMEOUT_SECONDS", "300"))
RENDER_FPS = int(os.environ.get("RENDER_FPS", "30"))
RENDER_DEFAULT_WIDTH = int(os.environ.get("RENDER_WIDTH", "1280"))
RENDER_DEFAULT_HEIGHT = int(os.environ.get("RENDER_HEIGHT", "720"))
RENDER_BEARER_TOKEN = os.environ.get("RENDER_BEARER_TOKEN", "").strip()
VIDEO_TTL_SECONDS = int(os.environ.get("RENDER_VIDEO_TTL_SECONDS", "3600"))

OUTPUT_DIR = Path(os.environ.get("RENDER_OUTPUT_DIR", "/opt/news_radio_24_7/render_output"))
ROOT_DIR = Path(__file__).resolve().parent
WEB_DIR = ROOT_DIR.parent / "web"

LIVE2D_VENDOR_DIR = Path(os.environ.get("LIVE2D_VENDOR_DIR", str(WEB_DIR / "vendor" / "live2d")))
LIVE2D_MODEL_DIR  = Path(os.environ.get("LIVE2D_MODEL_DIR",  str(WEB_DIR / "live2d")))

# CDN sources for Live2D vendor JS files.
# These are downloaded once on startup (if missing) and then served locally.
LIVE2D_VENDOR_CDNS: dict[str, str] = {
    "live2dcubismcore.min.js": "https://cubism.live2d.com/sdk-web/cubismcore/live2dcubismcore.min.js",
    "pixi.min.js":             "https://cdn.jsdelivr.net/npm/pixi.js@6.5.10/dist/browser/pixi.min.js",
    "cubism4.min.js":          "https://cdn.jsdelivr.net/npm/pixi-live2d-display@0.4.0/dist/cubism4.min.js",
}

DISPLAY_LOCK = threading.Lock()
USED_DISPLAYS: set[str] = set()
ACTIVE_RENDER_DIRS: dict[str, Path] = {}
ACTIVE_RENDER_LOCK = threading.Lock()

app = Flask(__name__)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _ensure_live2d_vendor() -> None:
    """Download Live2D vendor JS files from CDN if they are not present locally.

    The files are only downloaded once; on subsequent starts they are already on
    disk and the function returns immediately.  Failures are logged as warnings
    so a missing internet connection does not prevent the server from starting
    (the avatar will simply be absent from those renders).
    """
    LIVE2D_VENDOR_DIR.mkdir(parents=True, exist_ok=True)
    for filename, url in LIVE2D_VENDOR_CDNS.items():
        dest = LIVE2D_VENDOR_DIR / filename
        if dest.exists():
            continue
        app.logger.info("Live2D vendor: descargando %s …", filename)
        result = subprocess.run(
            [
                "curl", "--fail", "--location", "--silent", "--show-error",
                "--max-time", "60", "--output", str(dest), url,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            app.logger.warning(
                "Live2D vendor: no se pudo descargar %s: %s",
                filename, result.stderr.strip(),
            )
        else:
            app.logger.info("Live2D vendor: %s descargado OK", filename)

# Invocada al importar el módulo para que los archivos estén disponibles
# independientemente de cómo se inicie Flask (directamente o vía gunicorn/uwsgi).
# La función es idempotente: solo descarga archivos que faltan.
_ensure_live2d_vendor()
VIDEO_FILENAME_RE = re.compile(r"^[a-f0-9]{32}\.mp4$")
TMP_ASSET_RE = re.compile(r"^([a-f0-9]{32})/(audio\.mp3|bg\.jpg)$")


def _json_error(message: str, status: int = 400):
    return jsonify({"ok": False, "error": message}), status


def _is_authorized() -> bool:
    if not RENDER_BEARER_TOKEN:
        return True  # No token configured → open access
    auth_header = request.headers.get("Authorization", "")
    expected = f"Bearer {RENDER_BEARER_TOKEN}"
    return secrets.compare_digest(auth_header, expected)


def _cleanup_old_videos() -> None:
    now = time.time()
    for file_path in OUTPUT_DIR.glob("*.mp4"):
        try:
            if now - file_path.stat().st_mtime > VIDEO_TTL_SECONDS:
                file_path.unlink(missing_ok=True)
        except Exception:
            pass


def _cleanup_loop() -> None:
    while True:
        _cleanup_old_videos()
        time.sleep(600)


def _is_public_http_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    if not parsed.hostname:
        return False
    try:
        records = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror:
        return False
    for record in records:
        candidate = record[4][0]
        parsed_ip = ip_address(candidate)
        if (
            parsed_ip.is_private
            or parsed_ip.is_loopback
            or parsed_ip.is_link_local
            or parsed_ip.is_multicast
            or parsed_ip.is_reserved
            or parsed_ip.is_unspecified
        ):
            return False
    return True


def _allocate_display() -> str:
    with DISPLAY_LOCK:
        for number in range(99, 150):
            display = f":{number}"
            if display not in USED_DISPLAYS:
                USED_DISPLAYS.add(display)
                return display
    raise RuntimeError("No hay displays disponibles para renderizar")


def _release_display(display: str) -> None:
    with DISPLAY_LOCK:
        USED_DISPLAYS.discard(display)


def _start_xvfb(display: str, width: int, height: int):
    cmd = ["Xvfb", display, "-screen", "0", f"{width}x{height}x24", "-nolisten", "tcp"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(0.6)
    if proc.poll() is not None:
        stderr = (proc.stderr.read() or b"").decode("utf-8", errors="replace")
        raise RuntimeError(f"No se pudo iniciar Xvfb: {stderr.strip()}")
    return proc


def _resolve_dimensions(form_data):
    width = form_data.get("width")
    height = form_data.get("height")
    if width and height:
        try:
            return max(360, min(3840, int(width))), max(360, min(3840, int(height)))
        except ValueError:
            pass
    mode = (form_data.get("resolution") or form_data.get("orientation") or "").strip().lower()
    if mode in {"vertical", "shorts", "1080x1920", "9:16"}:
        return 1080, 1920
    return RENDER_DEFAULT_WIDTH, RENDER_DEFAULT_HEIGHT


def _download_file(url: str, output_path: Path) -> None:
    if not _is_public_http_url(url):
        raise RuntimeError("URL de imagen no permitida")
    result = subprocess.run(
        ["curl", "--fail", "--location", "--silent", "--show-error", "--max-time", "30",
         "--proto", "=https,http", "--output", str(output_path), url],
        check=False, capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"No se pudo descargar imageUrl: {result.stderr.strip()}")


def _render_video(temp_dir, output_path, title, subtitle, bg_path, width, height, job_id):
    display = _allocate_display()
    xvfb_proc = None
    ffmpeg_proc = None
    try:
        xvfb_proc = _start_xvfb(display, width, height)
        audio_relative = f"/tmp/{job_id}/audio.mp3"
        bg_relative = f"/tmp/{job_id}/bg.jpg" if bg_path else ""
        query = urlencode({"audio": audio_relative, "bg": bg_relative, "title": title, "subtitle": subtitle})
        capture_url = f"http://127.0.0.1:{RENDER_PORT}/capture.html?{query}"
        ffmpeg_cmd = [
            "ffmpeg", "-y", "-f", "x11grab", "-r", str(RENDER_FPS),
            "-s", f"{width}x{height}", "-i", display,
            "-i", str(temp_dir / "audio.mp3"),
            "-c:v", "libx264", "-preset", "veryfast",
            "-c:a", "aac", "-shortest", str(output_path),
        ]
        ffmpeg_env = os.environ.copy()
        ffmpeg_env["DISPLAY"] = display
        browser_env = os.environ.copy()
        browser_env["DISPLAY"] = display
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False, env=browser_env,
                args=["--autoplay-policy=no-user-gesture-required",
                      f"--window-size={width},{height}", "--disable-dev-shm-usage"],
            )
            context = browser.new_context(viewport={"width": width, "height": height})
            page = context.new_page()
            page.goto(capture_url, wait_until="domcontentloaded", timeout=60_000)
            # Wait until the page background has loaded and layout is painted.
            # This prevents FFmpeg from recording blank frames at the start.
            page.wait_for_function("() => window.__pageReady === true", timeout=30_000)
            # Start FFmpeg NOW — the page is already visible on the Xvfb display.
            ffmpeg_proc = subprocess.Popen(
                ffmpeg_cmd, stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=ffmpeg_env,
            )
            # Brief ramp-up so FFmpeg has established its recording stream
            # before audio starts, avoiding any dropped frames at the very beginning.
            time.sleep(0.4)
            # Trigger audio playback and lipsync inside the page.
            page.evaluate("window.__startRender()")
            page.wait_for_function("() => window.__renderDone === true", timeout=RENDER_TIMEOUT_SECONDS * 1000)
            browser.close()
        if ffmpeg_proc.poll() is None and ffmpeg_proc.stdin:
            ffmpeg_proc.stdin.write(b"q\n")
            ffmpeg_proc.stdin.flush()
        _, stderr_output = ffmpeg_proc.communicate(timeout=60)
        if ffmpeg_proc.returncode != 0:
            stderr = (stderr_output or b"").decode("utf-8", errors="replace")
            raise RuntimeError(f"FFmpeg fallo: {stderr[-1200:]}")
    finally:
        if ffmpeg_proc and ffmpeg_proc.poll() is None:
            ffmpeg_proc.kill()
        if xvfb_proc and xvfb_proc.poll() is None:
            xvfb_proc.terminate()
            try:
                xvfb_proc.wait(timeout=3)
            except Exception:
                xvfb_proc.kill()
        _release_display(display)


@app.route("/render", methods=["POST"])
def render():
    if not _is_authorized():
        return _json_error("No autorizado", 401)
    _cleanup_old_videos()
    audio_file = request.files.get("audio")
    if not audio_file:
        return _json_error("Falta archivo audio", 400)
    temp_dir = Path(tempfile.mkdtemp(prefix="render_", dir="/tmp"))
    job_id = uuid.uuid4().hex
    with ACTIVE_RENDER_LOCK:
        ACTIVE_RENDER_DIRS[job_id] = temp_dir
    output_filename = f"{uuid.uuid4().hex}.mp4"
    output_path = OUTPUT_DIR / output_filename
    try:
        audio_path = temp_dir / "audio.mp3"
        audio_file.save(audio_path)
        image_url = (request.form.get("imageUrl") or "").strip()
        title = (request.form.get("title") or "").strip()
        subtitle = (request.form.get("subtitle") or title).strip()
        bg_path = None
        if image_url:
            bg_path = temp_dir / "bg.jpg"
            _download_file(image_url, bg_path)
        width, height = _resolve_dimensions(request.form)
        _render_video(temp_dir, output_path, title, subtitle, bg_path, width, height, job_id)
        return jsonify({"ok": True, "videoUrl": f"{RENDER_PUBLIC_URL}/videos/{output_filename}"})
    except Exception:
        app.logger.exception("Render failed")
        output_path.unlink(missing_ok=True)
        return _json_error("Error interno durante el render", 500)
    finally:
        with ACTIVE_RENDER_LOCK:
            ACTIVE_RENDER_DIRS.pop(job_id, None)
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.route("/videos/<filename>", methods=["GET"])
def get_video(filename: str):
    if not VIDEO_FILENAME_RE.fullmatch(filename):
        return _json_error("Archivo invalido", 400)
    return send_from_directory(OUTPUT_DIR, filename)


@app.route("/capture.html", methods=["GET"])
def capture_page():
    return send_from_directory(ROOT_DIR, "capture.html")


@app.route("/vendor/<path:filename>", methods=["GET"])
def vendor_files(filename: str):
    return send_from_directory(ROOT_DIR / "vendor", filename)


@app.route("/tmp/<path:asset_path>", methods=["GET"])
def serve_tmp_asset(asset_path: str):
    m = TMP_ASSET_RE.fullmatch(asset_path)
    if not m:
        return _json_error("Not found", 404)
    job_id = m.group(1)
    filename = m.group(2)
    with ACTIVE_RENDER_LOCK:
        temp_dir = ACTIVE_RENDER_DIRS.get(job_id)
    if not temp_dir:
        return _json_error("Not found", 404)
    return send_from_directory(str(temp_dir), filename)


@app.route("/live2d-vendor/<path:filename>", methods=["GET"])
def live2d_vendor(filename: str):
    if not LIVE2D_VENDOR_DIR.is_dir():
        return _json_error("Live2D vendor not found", 404)
    return send_from_directory(LIVE2D_VENDOR_DIR, filename)


@app.route("/live2d-model/<path:filename>", methods=["GET"])
def live2d_model(filename: str):
    if not LIVE2D_MODEL_DIR.is_dir():
        return _json_error("Live2D model not found", 404)
    return send_from_directory(LIVE2D_MODEL_DIR, filename)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True})


if __name__ == "__main__":
    threading.Thread(target=_cleanup_loop, daemon=True).start()
    app.run(host=RENDER_HOST, port=RENDER_PORT, threaded=True)
