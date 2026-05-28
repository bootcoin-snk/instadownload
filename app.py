from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from pathlib import Path
import yt_dlp
import uuid
import time
import subprocess
import shutil

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

def is_tiktok_url(url: str) -> bool:
    url = url.lower()
    return "tiktok.com" in url

def clean_old_files(max_age_hours=24):
    now = time.time()
    max_age = max_age_hours * 60 * 60

    for file in DOWNLOAD_DIR.glob("*"):
        if file.is_file() and now - file.stat().st_mtime > max_age:
            try:
                file.unlink()
            except Exception:
                pass

def convert_to_quicktime_mp4(input_file: Path, output_file: Path):
    """
    Conversão final manual para máxima compatibilidade:
    - vídeo H.264
    - áudio AAC
    - pixel format yuv420p
    - faststart
    - mapeia áudio se existir
    """
    if not FFMPEG_PATH:
        raise RuntimeError("FFmpeg não está disponível. Verifique se imageio-ffmpeg foi instalado.")

    cmd = [
        FFMPEG_PATH,
        "-y",
        "-i", str(input_file),

        "-map", "0:v:0",
        "-map", "0:a:0?",

        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",

        "-c:a", "aac",
        "-b:a", "192k",
        "-ac", "2",

        "-movflags", "+faststart",
        str(output_file)
    ]

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr[-2000:])

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

    if not FFMPEG_PATH:
        return jsonify({
            "error": "FFmpeg não está disponível no servidor.",
            "ffmpeg_available": False
        }), 500

    job_id = str(uuid.uuid4())[:8]
    raw_template = str(DOWNLOAD_DIR / f"{job_id}-raw.%(ext)s")
    final_filename = f"{job_id}-social-downloader.mp4"
    final_path = DOWNLOAD_DIR / final_filename

    # TikTok costuma funcionar melhor priorizando arquivo único com áudio.
    # Instagram costuma precisar de vídeo+áudio separados e merge.
    if is_tiktok_url(url):
        format_selector = (
            "best[ext=mp4][vcodec!=none][acodec!=none]/"
            "best[vcodec!=none][acodec!=none]/"
            "bv*+ba/"
            "best"
        )
    else:
        format_selector = (
            "bv*[vcodec^=avc1]+ba/"
            "bv*+ba/"
            "best[ext=mp4][vcodec!=none][acodec!=none]/"
            "best"
        )

    ydl_opts = {
        "outtmpl": raw_template,
        "format": format_selector,
        "merge_output_format": "mp4",
        "ffmpeg_location": FFMPEG_PATH,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "overwrites": True,
    }

    try:
        before = set(DOWNLOAD_DIR.glob(f"{job_id}-raw*"))

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        after = set(DOWNLOAD_DIR.glob(f"{job_id}-raw*"))
        raw_files = sorted(after - before, key=lambda p: p.stat().st_mtime, reverse=True)

        # Fallback: em alguns casos o arquivo é criado mas também aparece no before.
        if not raw_files:
            raw_files = sorted(
                DOWNLOAD_DIR.glob(f"{job_id}-raw*"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )

        raw_files = [
            file for file in raw_files
            if file.is_file()
            and not file.name.endswith(".part")
            and not file.name.endswith(".ytdl")
            and file.name != final_filename
        ]

        if not raw_files:
            return jsonify({"error": "Download concluído, mas o arquivo bruto não foi encontrado."}), 500

        raw_file = raw_files[0]

        convert_to_quicktime_mp4(raw_file, final_path)

        # Limpa arquivos brutos do job depois da conversão.
        for file in DOWNLOAD_DIR.glob(f"{job_id}-raw*"):
            try:
                if file.name != final_filename:
                    file.unlink()
            except Exception:
                pass

        if not final_path.exists() or final_path.stat().st_size == 0:
            return jsonify({"error": "A conversão final falhou."}), 500

        return jsonify({
            "success": True,
            "filename": final_filename,
            "download_url": f"/downloads/{final_filename}",
            "ffmpeg_available": True
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