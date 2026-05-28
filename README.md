# Backend Flask - Social Downloader

Backend atualizado para converter os vídeos para MP4 compatível com Mac/QuickTime:
- Vídeo: H.264
- Áudio: AAC
- Container: MP4
- `faststart` ativado

## Render

Use:

```bash
Build Command:
./render-build.sh
```

```bash
Start Command:
gunicorn app:app
```

Se o Render reclamar de permissão no build script, use este Build Command:

```bash
chmod +x render-build.sh && ./render-build.sh
```

## Teste

Depois do deploy, abra:

```txt
https://sua-api.onrender.com/api/health
```

Deve retornar:

```json
{"ok": true}
```