# Paper Gen Monorepo

This repository is organized as a monorepo with separate frontend and backend projects.

```
./frontend  # Next.js 16 App Router UI
./backend   # Django 5 + DRF API
```

## Quick Start

### Frontend
```bash
cd frontend
npm install
npm run dev
```

### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

## Environment
- Frontend uses `NEXT_PUBLIC_API_BASE_URL` to talk to the backend (to be added in frontend `.env.local`).
- Backend uses `DATABASE_URL`, `OPENAI_API_KEY`, and other variables in `backend/.env`.

## Status
- Backend migration is in progress. Legacy Next.js backend code still exists inside `frontend/` and will be removed after verification.
