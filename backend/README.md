# Paper Gen Backend (Django)

This is the Django 5 + Django REST Framework backend for the Paper Gen monorepo.

## Requirements
- Python 3.11+
- PostgreSQL 14+
- pgvector extension enabled

## Setup
1. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

2. Create a `.env` file from `.env.example` and fill in values.

3. For local development the backend defaults to SQLite when `DATABASE_URL` is not set.

If you will use PostgreSQL + `pgvector`, enable the extension in your database before running migrations:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

4. Run migrations:

```bash
python manage.py makemigrations
python manage.py migrate
```

5. Start the backend:

```bash
python manage.py runserver 0.0.0.0:8000
```

## API Overview
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`
- `POST /api/documents/upload`
- `GET /api/projects/`
- `POST /api/projects/questions/save`
- `POST /api/generation/questions/stream`
- `POST /api/generation/answer-key`

## Notes
- Session-cookie auth is used, so the frontend must send credentials with requests.
- Streaming endpoints use Server-Sent Events (SSE).
