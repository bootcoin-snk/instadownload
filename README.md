# Backend Flask - Social Downloader

Versão robusta para Instagram + TikTok.

Correções:
- Usa `imageio-ffmpeg`, sem apt-get.
- Baixa o vídeo com `yt-dlp`.
- Depois converte manualmente o arquivo final para:
  - MP4
  - H.264
  - AAC
  - yuv420p
  - faststart

## Render

Use exatamente:

```bash
Build Command:
pip install -r requirements.txt
```

```bash
Start Command:
gunicorn app:app
```

Não use `apt-get`.

## Teste

Depois do deploy, abra:

```txt
https://instadownload-mfjw.onrender.com/api/health
```

Precisa aparecer:

```json
"ffmpeg_available": true
```

Depois teste novamente Instagram e TikTok.