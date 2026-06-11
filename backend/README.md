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
- `GET /api/accounts/profile` — Get current authenticated user profile
- `GET /api/accounts/dashboard` — (Alias) Get current authenticated user profile
- `GET /api/accounts/users` — List local users (Admin only)
- `POST /api/accounts/users/<user_id>/approve` — Approve user in Cognito and locally (Admin only)
- `POST /api/accounts/users/<user_id>/reject` — Reject/disable user in Cognito and locally (Admin only)
- `POST /api/documents/upload`
- `GET /api/projects/`
- `POST /api/projects/questions/save`
- `POST /api/generation/questions/stream`
- `POST /api/generation/answer-key`

## Notes
- AWS Cognito JWT token-based authentication is used. The frontend must pass the JWT in the `Authorization: Bearer <JWT>` header.
- Streaming endpoints use Server-Sent Events (SSE).

## S3 / MinIO Storage

This project can use S3-compatible object storage for media (PDF images, extracted files).

Environment variables (add to `.env`):

- `AWS_STORAGE_BUCKET_NAME` — bucket name to enable S3 storage (if unset, local `MEDIA_ROOT` is used)
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` — credentials for S3 or MinIO
- `AWS_S3_ENDPOINT_URL` — set to `http://localhost:9000` for a local MinIO instance
- `AWS_S3_REGION_NAME` — optional (default `us-east-1`)
- `AWS_QUERYSTRING_EXPIRE` — presigned URL expiry in seconds (default 3600)

For local development using MinIO, run:

```bash
docker run -p 9000:9000 -e MINIO_ROOT_USER=minio -e MINIO_ROOT_PASSWORD=minio123 \
	-v $(pwd)/minio-data:/data --name minio -d minio/minio server /data
```

Then set `AWS_S3_ENDPOINT_URL=http://localhost:9000`, `AWS_ACCESS_KEY_ID=minio`, and `AWS_SECRET_ACCESS_KEY=minio123`.

