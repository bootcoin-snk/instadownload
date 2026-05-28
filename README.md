# Backend Flask - Social Video Downloader

## Rodar local

```bash
cd backend-flask
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Teste:
```bash
curl http://localhost:5001/api/health
```

## Deploy sugerido

Use Render, Railway, Fly.io ou VPS.

Comando de start:
```bash
gunicorn app:app
```

Depois copie a URL pública do backend e troque no arquivo:

```js
const API_BASE_URL = "https://sua-api.com";
```

em `frontend-netlify/script.js`.