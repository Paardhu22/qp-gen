# Deploying the Question Pool architecture

Runbook for moving the live EC2 host onto the pool pipeline. Read the rollback
section before you start.

## What changes at runtime

| | Before | After |
|---|---|---|
| LLM calls per paper | ~38 (one per blueprint slot) | 4 (Model 1) + 1 (image specs) + 1 (Model 2) |
| Questions produced | ~38 | ~84, all saved to the bank |
| Saving | manual, behind a checkbox | automatic, every generation |
| Re-papering a chapter | full regeneration | 1 call via `paper-from-bank` |

Text generation gets roughly 10× cheaper. **Image questions do not** — see the
cost section, they dominate the bill at the default setting.

## 1. Database migration

Two migrations, both against the `Question` table:

- `projects/0006` — adds `explanation`, `imageUrl`, `userId`, `contentHash`,
  `poolId`, `sourceType`, `metadata`, plus three indexes.
- `projects/0007` — backfills `userId` from the owning project.

Adding nullable columns is instant on Postgres 11+. The three `CREATE INDEX`
statements take a lock for the duration of the build. On a table of a few
thousand rows that is milliseconds; if `Question` has grown large, check first:

```bash
psql "$DATABASE_URL" -c "SELECT count(*) FROM \"Question\";"
```

Above ~1M rows, build the indexes concurrently by hand *before* running
`migrate`, then fake the migration:

```sql
CREATE INDEX CONCURRENTLY question_user_subj_class_idx ON "Question" ("userId", subject, "gradeClass");
CREATE INDEX CONCURRENTLY question_user_hash_idx      ON "Question" ("userId", "contentHash");
CREATE INDEX CONCURRENTLY question_pool_idx           ON "Question" ("poolId");
```

```bash
python manage.py migrate projects 0006 --fake
python manage.py migrate projects 0007
```

Otherwise just:

```bash
cd /path/to/backend
source venv/bin/activate
python manage.py migrate
```

`0007` is a single correlated UPDATE, not a row-by-row loop, so it does not
scale with round-trip latency.

**`Question.options` is untouched.** It stays a Postgres `text[]`.
`PortableArrayField` deconstructs as `ArrayField`, so `makemigrations` reports
no change — it exists only so SQLite tests can write a non-empty option list.

## 2. Environment

Add to `backend/.env`:

```bash
POOL_MODEL=gpt-4.1-mini
CHAPTER_MD_MAX_CHARS=240000

IMAGE_QUESTION_STRATEGY=generate
IMAGE_QUESTIONS_PER_POOL=8
OPENAI_IMAGE_MODEL=gpt-image-1
OPENAI_IMAGE_SIZE=1024x1024
IMAGE_COST_USD_PER_IMAGE=0.04
```

Every one of these has a working default, so a missed variable degrades rather
than crashes. `POOL_MODEL` defaulting to `gpt-4.1-mini` is the only one worth
double-checking — if your OpenAI account lacks access to it, set it to a model
you do have.

`gpt-image-1` requires a **verified** OpenAI organisation. If yours is not
verified the image stage will fail every call, log the failures, and produce a
text-only pool. Generation still succeeds. To avoid the wasted calls entirely,
set `IMAGE_QUESTIONS_PER_POOL=0` or `IMAGE_QUESTION_STRATEGY=reuse`.

## 3. Deploy

```bash
git pull
cd backend && source venv/bin/activate
pip install -r requirements.txt          # no new dependencies, but keep in sync
python manage.py migrate
python manage.py check --deploy
sudo systemctl restart qpgen             # or qp-gen-backend, per your unit name

cd ../frontend
npm ci
npm run build
sudo systemctl restart qpgen-frontend    # or however Next.js is supervised
```

No nginx change. The SSE endpoint and headers are unchanged, and
`X-Accel-Buffering: no` is still set on the response.

## 4. Smoke test

```bash
# 1. Bank summary should return 200 with a (possibly empty) chapter list.
curl -s -H "Authorization: Bearer $ID_TOKEN" \
  https://api.hsatedu.in/api/generation/bank-summary | head -c 400
```

Then in the browser: upload one chapter, generate a paper, and check that

- a progress line appears while the pool is being written,
- the paper renders with the expected question and mark counts,
- a green "N questions saved to your question bank" panel appears,
- the question-bank page now lists that chapter,
- "Create paper" from that chapter produces a paper **without** an upload.

Watch the backend log for the one-line summaries:

```bash
journalctl -u qpgen -f | grep -E "MODEL1|MODEL2|IMAGE_MODEL|POOL_"
```

`Model 1 finished: … produced=84 duplicates=3 invalid=1 failures=[]` is healthy.
A non-empty `failures` list, or `produced` far below target, means batches are
erroring — check the model name and the API key's rate limits.

## 5. Cost

Per generation at the defaults, roughly:

| Stage | Calls | Approx cost |
|---|---|---|
| Model 1 (4 batches, chapter cached after the first) | 4 | ~$0.04 |
| Image specs | 1 | ~$0.01 |
| **Image rendering (8 × gpt-image-1)** | **8** | **~$0.32** |
| Model 2 review | 1 | ~$0.01 |
| **Total** | | **~$0.38** |

Images are ~85% of it. Two levers, both env-only:

- `IMAGE_QUESTION_STRATEGY=hybrid` — uses the chapter's own extracted figures
  first and only synthesises what it cannot cover. Usually cuts image spend by
  most of that, and the figures are the real textbook ones.
- `IMAGE_QUESTIONS_PER_POOL=4` — halves it directly.

Synthesised diagrams are cached by prompt hash in
`generated_diagrams/<sha256>.png`, so regenerating a chapter reuses them.

Per-call spend is recorded in `ApiUsage` with an `operation` label
(`pool_model1_objective`, `pool_image_specs`, `pool_model2_review`, …):

```sql
SELECT operation, count(*), sum(total_tokens)
FROM "ApiUsage" WHERE "createdAt" > now() - interval '1 day'
GROUP BY operation ORDER BY 3 DESC;
```

Streamed calls were previously recorded as *nothing at all*, so this table is
newly meaningful — do not compare its totals against last week's.

## 6. Rollback

The cutover is one commit on top of a working tree, so:

```bash
git revert --no-commit b4a94f3   # legacy removal
git revert --no-commit 0b0a046   # pipeline wiring
git commit -m "revert: back to the per-slot engine"
# redeploy as in step 3
```

**Do not roll the migrations back.** `0006`/`0007` are purely additive; the
pre-pool code ignores the new columns entirely, so leaving them applied is safe
and avoids destroying auto-saved questions. If you must:
`python manage.py migrate projects 0005`.

Questions saved during the pool period stay in the bank and remain visible in
the UI after a revert — they are ordinary `Question` rows.

## Known gaps

- **Curriculum fallback is gone.** The old engine generated from CBSE
  curriculum knowledge when retrieval could not cover a slot. Model 1 reads the
  whole chapter, so coverage is far better, but a blueprint slot the chapter
  genuinely cannot support is now reported as unfilled (a `notice` event) rather
  than filled from general knowledge. The `content_scope_policy` payload field
  is accepted and ignored.
- **Language-subject validation** (`services/language_validation.py`) ran
  per-slot in the old engine and has no equivalent hook in the pool path.
  Grammar/composition/passage questions are generated but not re-validated.
- Both are tracked as follow-ups; neither blocks Science/Social Science/Maths,
  which is the bulk of usage.
