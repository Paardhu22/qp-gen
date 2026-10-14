# Backend

Django 5 + DRF API for qp-gen. Start at the [root README](../README.md) for the
repo map and quickstart.

```
config/     settings (every knob is an env var), urls, wsgi/asgi
apps/       Django apps — models, serializers, views, urls, management commands
services/   the business logic, grouped by domain (see services/README.md)
assets/     static files the backend ships (the email logo)
```

## Run

Requires Python 3.11+, PostgreSQL 14+ with the `vector` extension.
`DATABASE_URL` is **required** — settings refuse to start without it (only
`manage.py test` swaps in in-memory SQLite).

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # fill in DATABASE_URL, OPENAI_API_KEY, AWS_COGNITO_*
python manage.py migrate        # enables pgvector (the DB role must be allowed CREATE EXTENSION)
python manage.py runserver 0.0.0.0:8000
```

## Test

```bash
python manage.py test --noinput                        # everything
python manage.py test services.generation.pool         # one package
python manage.py test apps.organizations               # one app
python manage.py export_question_types --check         # frontend catalogue in sync?
```

## Management commands

`seed_superadmin` · `export_question_types` · `purge_deleted_papers` ·
`purge_expired_drafts` · `purge_generation_runs` · `backfill_set_content_to_s3` ·
`verify_s3` · `verify_email` · `strip_vi_from_chunks`

The three `purge_*` commands run daily from `deployment/qp-gen-retention.timer`.
