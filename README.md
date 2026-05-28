# Backend Flask - Social Downloader

Versão corrigida para Render.

Esta versão usa `imageio-ffmpeg`, então não precisa instalar FFmpeg com `apt-get`.

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

Não use:

```bash
apt-get install ffmpeg
```

## Teste

Depois do deploy, abra:

```txt
https://instadownload-mfjw.onrender.com/api/health
```

O ideal é retornar algo como:

```json
{
  "ok": true,
  "ffmpeg_available": true
}
```

Se `ffmpeg_available` vier `false`, o Render não instalou as dependências corretamente.