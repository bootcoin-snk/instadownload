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

def convert_to_quicktime_mp4(input_file: Path, output_file: Path, timeout=300):
    """
    Conversão final com múltiplas estratégias de fallback para compatibilidade máxima.
    Tenta: 1) Copiar sem re-encoding, 2) Re-encoding rápido, 3) Vídeo-only
    """
    if not FFMPEG_PATH:
        raise RuntimeError("FFmpeg não está disponível. Verifique se imageio-ffmpeg foi instalado.")

    strategies = [
        # Estratégia 1: Copiar sem re-encoding (mais rápido para TikTok)
        {
            "name": "direct_copy",
            "cmd": [
                FFMPEG_PATH, "-y", "-i", str(input_file),
                "-map", "0:v:0", "-map", "0:a?",
                "-c:v", "copy", "-c:a", "copy",
                "-movflags", "+faststart",
                str(output_file)
            ]
        },
        # Estratégia 2: Re-encoding ultra-rápido
        {
            "name": "ultrafast_encode",
            "cmd": [
                FFMPEG_PATH, "-y", "-i", str(input_file),
                "-map", "0:v:0", "-map", "0:a?",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k", "-ac", "2",
                "-movflags", "+faststart",
                str(output_file)
            ]
        },
        # Estratégia 3: Vídeo-only (fallback final)
        {
            "name": "video_only",
            "cmd": [
                FFMPEG_PATH, "-y", "-i", str(input_file),
                "-map", "0:v:0",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                str(output_file)
            ]
        }
    ]

    last_error = None
    for strategy in strategies:
        try:
            result = subprocess.run(
                strategy["cmd"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout
            )

            if result.returncode == 0:
                return  # Sucesso!
            else:
                last_error = result.stderr[-500:] if result.stderr else "Unknown error"
                # Continua para próxima estratégia
        except subprocess.TimeoutExpired:
            last_error = f"Timeout after {timeout}s"
            # Continua para próxima estratégia
        except Exception as e:
            last_error = str(e)
            # Continua para próxima estratégia

    # Se chegou aqui, todas as estratégias falharam
    raise RuntimeError(f"FFmpeg failed all strategies. Last error: {last_error}")

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
            "best[ext=mp4]/best"  # Preferir MP4 já pronto para evitar conversão
        )
    else:
        format_selector = (
            "bv[ext=mp4]+ba[ext=m4a]/"
            "bv*[vcodec^=avc1]+ba[ext=m4a]/"
            "bv*+ba/"
            "best[ext=mp4][vcodec!=none][acodec!=none]/"
            "best"
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

        # Otimização: Se o arquivo já é MP4, apenas renomeia (evita conversão demorada)
        if raw_file.suffix.lower() == ".mp4":
            try:
                shutil.copy2(raw_file, final_path)
                # Limpa arquivo bruto
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
            except Exception as e:
                pass  # Se copiar falhar, continua com conversão

        # Conversão necessária (arquivo não é MP4 ou cópia falhou)
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