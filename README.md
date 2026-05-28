# Backend Flask - Social Downloader

Correção para TikTok sem áudio.

Esta versão prioriza baixar arquivos que já venham com vídeo + áudio juntos,
o que resolve o caso comum do TikTok. Quando necessário, ainda usa FFmpeg via
`imageio-ffmpeg` para mesclar e converter para MP4 compatível com Mac/QuickTime.

## Render

Use:

```bash
Build Command:
pip install -r requirements.txt
```

```bash
Start Command:
gunicorn app:app
```

## Teste

Depois do deploy:

```txt
https://instadownload-mfjw.onrender.com/api/health
```

O ideal é retornar:

```json
{
  "ok": true,
  "ffmpeg_available": true
}
```