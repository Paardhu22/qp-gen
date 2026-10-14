# services/

The business logic. `apps/` handles HTTP and the database; anything with a
rule in it lives here, in one package per domain.

| Package | What it does |
|---|---|
| `generation/` | Turning a request into a paper. `planner/` builds the slot list, `pool/` generates and selects questions (the production path), `assets/` writes English reading/grammar/writing, `figures/` draws charts, `blueprint/` holds the CBSE rules engine, `rules/` the syllabus/language/content checks, `runs.py` makes generation durable |
| `sources/` | Everything about source material: PDF upload, OCR, chunking, embeddings, retrieval, readiness checks, and the shared HSAT textbook library (`hsat/`) |
| `papers/` | Projects, papers, drafts, the S3 copy of paper content, answer scripts |
| `templates/` | Paper templates: the spec, the built-in catalogue, class starters, and prose → paper design |
| `question_types/` | The question-type catalogue (no Django imports). Exports to the DB seed and to the frontend |
| `organizations/` | Brand kit, school logo, monthly token limits, token → INR pricing |
| `auth/` | Cognito and transactional email |
| `storage/` | S3 client and media-URL minting (the one authority — never persist presigned URLs) |
| `llm/` | The OpenAI client (usage recording) and the provider interface the pool pipeline uses |
| `chat.py` | The dashboard assistant. It converses; it never generates questions |

## Reading order for generation

`planner/` → `pool/pipeline.py` → `pool/model1.py` → `pool/model2.py`.
`planner/__init__.py` lists the planner modules in dependency order.

## Layering

```
apps/*  →  services/*  →  models
```

- Services may import `apps.*.models`; nothing under `apps/` models imports a service.
- Inside `services/`, `generation/` may use `sources/`, `templates/`, `question_types/`,
  `llm/`, `storage/` and `organizations/`. Keep the arrows pointing down.
- Tests live in a `tests/` folder in the package they cover.
