from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from pathlib import Path
import yt_dlp
import uuid
import time
import os

try:
    import imageio_ffmpeg
    FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG_PATH = None

app = Flask(__name__)
CORS(app, origins=["*"])

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_DOMAINS = [
    "instagram.com",
    "www.instagram.com",
    "tiktok.com",
    "www.tiktok.com",
    "vm.tiktok.com",
    "vt.tiktok.com",
]

def is_allowed_url(url: str) -> bool:
    url = url.lower()
    return url.startswith("http") and any(domain in url for domain in ALLOWED_DOMAINS)

def clean_old_files(max_age_hours=24):
    now = time.time()
    max_age = max_age_hours * 60 * 60

    for file in DOWNLOAD_DIR.glob("*"):
        if file.is_file() and now - file.stat().st_mtime > max_age:
            try:
                file.unlink()
            except Exception:
                pass

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "ok": True,
        "ffmpeg_available": bool(FFMPEG_PATH),
        "ffmpeg_path": FFMPEG_PATH
    })

@app.route("/api/download", methods=["POST"])
def download_video():
    clean_old_files()

    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()

    if not url:
        return jsonify({"error": "Cole uma URL válida."}), 400

    if not is_allowed_url(url):
        return jsonify({"error": "Esta ferramenta aceita apenas links do Instagram ou TikTok."}), 400

    job_id = str(uuid.uuid4())[:8]
    output_template = str(DOWNLOAD_DIR / f"{job_id}-%(title).120s.%(ext)s")

    ydl_opts = {
        "outtmpl": output_template,
        "format": "bv*[vcodec^=avc1]+ba[acodec^=mp4a]/b[ext=mp4]/bv*+ba/b",
        "merge_output_format": "mp4",
        "recodevideo": "mp4",
        "postprocessor_args": {
            "VideoConvertor": [
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k",
                "-movflags", "+faststart"
            ]
        },
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }

    if FFMPEG_PATH:
        ydl_opts["ffmpeg_location"] = FFMPEG_PATH

    try:
        before = set(DOWNLOAD_DIR.glob("*"))

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        after = set(DOWNLOAD_DIR.glob("*"))
        new_files = sorted(after - before, key=lambda p: p.stat().st_mtime, reverse=True)

        mp4_files = [
            file for file in new_files
            if file.suffix.lower() == ".mp4" and not file.name.endswith(".part")
        ]

        if not mp4_files:
            return jsonify({
                "error": "O vídeo foi baixado, mas não foi convertido corretamente para MP4.",
                "ffmpeg_available": bool(FFMPEG_PATH),
                "ffmpeg_path": FFMPEG_PATH
            }), 500

        filename = mp4_files[0].name

        return jsonify({
            "success": True,
            "filename": filename,
            "download_url": f"/downloads/{filename}",
            "ffmpeg_available": bool(FFMPEG_PATH)
        })

    except Exception as e:
        return jsonify({
            "error": "Não foi possível baixar/converter este vídeo.",
            "details": str(e),
            "ffmpeg_available": bool(FFMPEG_PATH),
            "ffmpeg_path": FFMPEG_PATH
        }), 500

@app.route("/downloads/<path:filename>", methods=["GET"])
def serve_download(filename):
    return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)