# qp-gen

A CBSE-compliant, AI-assisted question-paper generator. Teachers pick a
template (or describe a paper in their own words), point it at textbook
chapters, and get a printable paper they can edit in the browser and export to
PDF or DOCX.

| | |
|---|---|
| **Backend** | Django 5 + DRF, PostgreSQL + pgvector, OpenAI, AWS Cognito + S3 |
| **Frontend** | Next.js 16 (App Router), React 19, TipTap editor, Zustand |

## Repo map

```
backend/    Django API
  apps/       thin Django apps: models, serializers, views, urls
  services/   the logic, grouped by domain  → backend/services/README.md
  config/     settings (all env-driven), urls, wsgi
frontend/   Next.js app
  app/        routes only
  features/   one folder per product area   → frontend/README.md
  components/ shared UI primitives and app shell
  lib/        API clients and small helpers
deployment/ nginx, gunicorn + retention systemd units, db backup, runbook
docs/       long-form architecture + design records  → docs/README.md
```

**Where do I find …?**

| I want to change … | Look in |
|---|---|
| how a paper is planned from a request | `backend/services/generation/planner/` |
| how questions are generated and selected | `backend/services/generation/pool/` |
| PDF upload, OCR, chunking, retrieval | `backend/services/sources/` |
| templates and the Blueprint Builder | `backend/services/templates/` · `frontend/features/templates/`, `features/generation/blueprint/` |
| the list of question types | `backend/services/question_types/` (generated into `frontend/features/question-types/`) |
| the paper editor | `frontend/features/editor/` |
| an API endpoint | `backend/apps/<app>/urls.py` → `views` · client in `frontend/lib/api/` |
| login, schools, invites, usage limits | `backend/apps/organizations/` · `backend/services/auth/` · `frontend/features/auth/`, `features/admin/` |
| PDF / DOCX export | `frontend/features/export/` |

## Run it locally

**Backend** (needs PostgreSQL with pgvector available and a filled-in `.env`):

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env           # set DATABASE_URL, OPENAI_API_KEY, AWS_COGNITO_*
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev                    # http://localhost:3000
```

Set `NEXT_PUBLIC_API_BASE_URL` and the `NEXT_PUBLIC_AWS_COGNITO_*` values in
`frontend/.env`.

## Test it

```bash
# backend: ~1,200 tests, ~20 s, runs on in-memory SQLite (never touches your DB)
cd backend && venv/bin/python manage.py test --noinput

# frontend
cd frontend && npm run typecheck && npm run lint && npm test
```

`npm test` runs the node self-checks in `frontend/scripts/`. A change to the
question-type catalogue also needs `python manage.py export_question_types --check`.

## Conventions

- **Apps are thin, services are fat.** Views validate and serialize; anything
  with a rule in it lives in `backend/services/<domain>/`. Services may import
  models; models never import services.
- **Tests sit beside the code** in a `tests/` folder (`services/<pkg>/tests/`),
  or in `tests.py` / `test_*.py` for Django apps.
- **Frontend features own their pieces.** A feature folder holds its
  components, hooks and logic together; `components/ui` and `lib/` are for
  things used by several features. `app/` pages stay thin.
- **One place per concern.** There is one export path, one SSE reader, one
  media-URL authority. Look for it before writing a second.

## Further reading

[`docs/architecture.md`](docs/architecture.md) is the full technical
reference: the two-layer generation model, the pool pipeline, durable runs, the
data model, deployment, and the trade-offs behind each.
