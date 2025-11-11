# Flask Backend Scaffold

This is a minimal Flask scaffold created to replace the Node.js backend.

Quick start (macOS / zsh):

1. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies

```bash
pip install -r requirements.txt
```

3. Run the development server

```bash
# development
export FLASK_APP=app
export FLASK_ENV=development
flask run --host=0.0.0.0 --port=5001

# production-like (gunicorn)
gunicorn -w 2 -b 0.0.0.0:8000 app:app
```

Endpoints:

- `GET /health` - health check
- `GET /api/example` - example endpoint
