from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from pathlib import Path
import yt_dlp
import uuid
import time

app = Flask(__name__)

# Em produção, troque "*" pelo domínio do seu Netlify.
# Exemplo: CORS(app, origins=["https://sua-ferramenta.netlify.app"])
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
    return jsonify({"ok": True})

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

    # Versão compatível com Render Free:
    # sem apt-get e sem script de instalação do FFmpeg.
    # O yt-dlp tenta usar o FFmpeg disponível no ambiente para recodificar em MP4.
    ydl_opts = {
        "outtmpl": str(DOWNLOAD_DIR / f"{job_id}-%(title).120s.%(ext)s"),
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "recodevideo": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }

    try:
        before = set(DOWNLOAD_DIR.glob("*"))

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        after = set(DOWNLOAD_DIR.glob("*"))
        new_files = sorted(after - before, key=lambda p: p.stat().st_mtime, reverse=True)

        mp4_files = [file for file in new_files if file.suffix.lower() == ".mp4"]
        final_files = mp4_files or new_files

        if not final_files:
            return jsonify({"error": "Download concluído, mas o arquivo não foi encontrado."}), 500

        filename = final_files[0].name

        return jsonify({
            "success": True,
            "filename": filename,
            "download_url": f"/downloads/{filename}"
        })

    except Exception as e:
        return jsonify({
            "error": "Não foi possível baixar/converter este vídeo. Verifique se o link é público e autorizado.",
            "details": str(e)
        }), 500

@app.route("/downloads/<path:filename>", methods=["GET"])
def serve_download(filename):
    return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)