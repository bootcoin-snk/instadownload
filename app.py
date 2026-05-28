from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from pathlib import Path
import yt_dlp
import uuid
import time
import subprocess
import shutil
import json

try:
    import imageio_ffmpeg
    FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
    FFPROBE_PATH = getattr(imageio_ffmpeg, "get_ffprobe_exe", None)
    if callable(FFPROBE_PATH):
        try:
            FFPROBE_PATH = imageio_ffmpeg.get_ffprobe_exe()
        except Exception:
            FFPROBE_PATH = None
    else:
        FFPROBE_PATH = None
except Exception:
    FFMPEG_PATH = None
    FFPROBE_PATH = None

# Se o pacote imageio-ffmpeg não fornecer um executável, tente usar o FFmpeg do sistema.
if not FFMPEG_PATH:
    FFMPEG_PATH = shutil.which("ffmpeg")
if not FFPROBE_PATH:
    FFPROBE_PATH = shutil.which("ffprobe")

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


def probe_streams(input_file: Path):
    if not FFMPEG_PATH and not FFPROBE_PATH:
        return {"has_video": False, "has_audio": False, "streams": []}

    # Prefere ffprobe quando disponível, pois entrega JSON confiável.
    if FFPROBE_PATH:
        try:
            probe_cmd = [
                FFPROBE_PATH, "-v", "quiet", "-print_format", "json",
                "-show_format", "-show_streams", str(input_file)
            ]
            result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)
            data = json.loads(result.stdout) if result.stdout else {}
            streams = data.get("streams", [])
            has_video = any(s.get("codec_type") == "video" for s in streams)
            has_audio = any(s.get("codec_type") == "audio" for s in streams)
            return {"has_video": has_video, "has_audio": has_audio, "streams": streams}
        except Exception:
            pass

    # Fallback para ffmpeg quando ffprobe não está disponível.
    if FFMPEG_PATH:
        try:
            probe_cmd = [
                FFMPEG_PATH, "-hide_banner", "-loglevel", "error",
                "-i", str(input_file)
            ]
            result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)
            stderr = result.stderr or ""
            streams = []
            for line in stderr.splitlines():
                if "Stream #" in line:
                    if "Video:" in line:
                        streams.append({"codec_type": "video"})
                    elif "Audio:" in line:
                        streams.append({"codec_type": "audio"})
            has_video = any(s.get("codec_type") == "video" for s in streams)
            has_audio = any(s.get("codec_type") == "audio" for s in streams)
            return {"has_video": has_video, "has_audio": has_audio, "streams": streams}
        except Exception:
            pass

    return {"has_video": False, "has_audio": False, "streams": []}


def convert_to_quicktime_mp4(input_file: Path, output_file: Path, timeout=300):
    """
    Conversão final com suporte robusto para áudio.
    Detecta streams e escolhe a melhor estratégia.
    """
    if not FFMPEG_PATH:
        raise RuntimeError("FFmpeg não está disponível. Verifique se imageio-ffmpeg foi instalado.")

    # Detecta streams disponíveis no arquivo
    probe = probe_streams(input_file)
    has_video = probe.get("has_video", False)
    has_audio = probe.get("has_audio", False)
    audio_streams = [s for s in probe.get("streams", []) if s.get("codec_type") == "audio"]

    # Estratégia 1: Com áudio (se disponível)
    if has_audio and audio_streams:
        cmd = [
            FFMPEG_PATH,
            "-y",
            "-i", str(input_file),
            "-map", "0:v:0",
            "-map", "0:a:0",  # Pega primeiro stream de áudio
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
        
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout
            )
            
            if result.returncode == 0:
                return  # Sucesso!
        except subprocess.TimeoutExpired:
            pass
        except Exception:
            pass

    # Estratégia 2: Tenta com qualquer áudio disponível
    if has_audio:
        cmd = [
            FFMPEG_PATH,
            "-y",
            "-i", str(input_file),
            "-map", "0:v:0",
            "-map", "0:a?",  # Qualquer áudio
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "28",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "128k",
            "-ac", "2",
            "-movflags", "+faststart",
            str(output_file)
        ]
        
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout
            )
            
            if result.returncode == 0:
                return  # Sucesso!
        except subprocess.TimeoutExpired:
            pass
        except Exception:
            pass

    # Estratégia 3: Vídeo-only (último recurso)
    cmd = [
        FFMPEG_PATH,
        "-y",
        "-i", str(input_file),
        "-map", "0:v:0",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "28",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output_file)
    ]
    
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout
        )
        
        if result.returncode == 0:
            return  # Sucesso!
        else:
            raise RuntimeError(f"FFmpeg failed: {result.stderr[-500:]}")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Conversão FFmpeg excedeu {timeout}s - arquivo muito grande")

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
    is_tiktok = is_tiktok_url(url)
    
    if is_tiktok:
        format_selector = (
            "bestvideo[ext=mp4]+bestaudio/bestvideo+bestaudio/best"
        )
    else:
        format_selector = (
            "bestvideo[ext=mp4]+bestaudio/bestvideo+bestaudio/best"
        )

    # Headers específicos para cada plataforma
    http_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    if is_tiktok:
        http_headers["Referer"] = "https://www.tiktok.com/"

    ydl_opts = {
        "outtmpl": raw_template,
        "format": format_selector,
        "merge_output_format": "mp4",
        "prefer_ffmpeg": True,
        "ffmpeg_location": FFMPEG_PATH,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "overwrites": True,
        "socket_timeout": 60,
        "http_headers": http_headers,
        "extractor_args": {},
        "retries": 3,
        "skip_unavailable_fragments": True,
    }
    
    # Configurações extras para TikTok
    if is_tiktok:
        ydl_opts["extractor_args"] = {
            "tiktok": ["--api-hostname=api16-normal-c-useast1a.tiktokv.com"]
        }

    try:
        before = set(DOWNLOAD_DIR.glob(f"{job_id}-raw*"))

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.download([url])

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
            error_msg = "Download concluído, mas o arquivo bruto não foi encontrado."
            if is_tiktok:
                error_msg += " TikTok pode estar bloqueando ou o vídeo pode estar indisponível."
            return jsonify({"error": error_msg}), 500

        raw_file = raw_files[0]
        
        # Verifica se o arquivo tem tamanho válido
        if raw_file.stat().st_size == 0:
            error_msg = "Arquivo baixado está vazio. O vídeo pode estar privado ou indisponível."
            if is_tiktok:
                error_msg = "TikTok bloqueou o download. Tente: 1) Clicar em outro vídeo e voltar 2) Usar uma URL diferente"
            return jsonify({"error": error_msg}), 400

        # Se o arquivo já é MP4 com áudio e vídeo, tenta remuxar para evitar problemas de container.
        if raw_file.suffix.lower() == ".mp4":
            probe = probe_streams(raw_file)
            if probe["has_video"] and probe["has_audio"]:
                success = False

                if FFMPEG_PATH:
                    try:
                        remux_cmd = [
                            FFMPEG_PATH,
                            "-y",
                            "-i", str(raw_file),
                            "-c", "copy",
                            "-movflags", "+faststart",
                            str(final_path),
                        ]
                        remux_result = subprocess.run(
                            remux_cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            timeout=120
                        )
                        if remux_result.returncode == 0 and final_path.exists() and final_path.stat().st_size > 0:
                            success = True
                    except Exception:
                        success = False

                if not success:
                    try:
                        shutil.copy2(raw_file, final_path)
                    except Exception:
                        success = False
                    else:
                        success = final_path.exists() and final_path.stat().st_size > 0

                if success:
                    for file in DOWNLOAD_DIR.glob(f"{job_id}-raw*"):
                        try:
                            if file.name != final_filename:
                                file.unlink()
                        except Exception:
                            pass
                    return jsonify({
                        "success": True,
                        "filename": final_filename,
                        "download_url": f"/downloads/{final_filename}",
                        "ffmpeg_available": True
                    })

        # FFmpeg conversão é necessária para preservar áudio e garantir compatibilidade
        try:
            convert_to_quicktime_mp4(raw_file, final_path)
        except subprocess.TimeoutExpired:
            return jsonify({"error": "Arquivo muito grande - conversão excedeu 10 minutos. Tente um vídeo menor."}), 408
        except Exception as e:
            return jsonify({"error": f"Falha ao processar áudio/vídeo: {str(e)}"}), 500

        # Limpa arquivos brutos do job depois da conversão.
        for file in DOWNLOAD_DIR.glob(f"{job_id}-raw*"):
            try:
                if file.name != final_filename:
                    file.unlink()
            except Exception:
                pass

        if not final_path.exists() or final_path.stat().st_size == 0:
            return jsonify({"error": "A conversão final falhou - arquivo vazio."}), 500

        return jsonify({
            "success": True,
            "filename": final_filename,
            "download_url": f"/downloads/{final_filename}",
            "ffmpeg_available": True
        })

    except Exception as e:
        error_str = str(e).lower()
        
        # Mensagens de erro específicas para TikTok
        if is_tiktok:
            if "403" in error_str or "forbidden" in error_str:
                return jsonify({
                    "error": "TikTok bloqueou este download (erro 403). Tente um vídeo diferente ou aguarde alguns minutos.",
                    "ffmpeg_available": bool(FFMPEG_PATH),
                }), 403
            elif "404" in error_str or "not found" in error_str:
                return jsonify({
                    "error": "Vídeo TikTok não encontrado. Verifique se a URL é válida ou se o vídeo foi deletado.",
                    "ffmpeg_available": bool(FFMPEG_PATH),
                }), 404
            elif "timeout" in error_str or "timed out" in error_str:
                return jsonify({
                    "error": "Conexão com TikTok expirou. A plataforma está lenta ou bloqueando. Tente novamente.",
                    "ffmpeg_available": bool(FFMPEG_PATH),
                }), 504
        
        return jsonify({
            "error": "Não foi possível baixar/converter este vídeo.",
            "details": error_str[:200],
            "ffmpeg_available": bool(FFMPEG_PATH),
        }), 500

@app.route("/downloads/<path:filename>", methods=["GET"])
def serve_download(filename):
    return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)