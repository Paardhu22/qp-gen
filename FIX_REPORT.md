# FIX_REPORT — Answer-script generation, intermittent figures, app-wide slowness

Three independent clusters, one commit per cluster, no regressions to the
prior round (OR-group A1/A2/grouped-OR/literal "1." typing, per-keystroke
save, StatusBar/marks debounces, Cluster B "Question visual" backend
rejection). 95/95 backend tests pass; frontend `tsc --noEmit` clean;
production build succeeds (Next 16.2.6 Turbopack, 7.0 s compile).

Commits (newest → oldest):
- `477d3d5` perf(auth): non-blocking session check on every protected-route nav
- `e6afc5b` fix(figures): resolve relative /media/ URLs + eradicate Question-visual alt
- `c51207a` fix(answer-script): remove unsupported temperature=0 + emit questionBlock nodes

---

## CLUSTER A — answer-script generation

### Real traceback (the swallowed exception)

Reproduced the failing call against the live OpenAI endpoint with the exact
kwargs `answer_script_service._generate_single_answer_llm_only` was sending:

```
BadRequestError: Error code: 400 - {'error': {'message':
  "Unsupported value: 'temperature' does not support 0 with this model.
   Only the default (1) value is supported.",
  'type': 'invalid_request_error',
  'param': 'temperature',
  'code': 'unsupported_value'}}
```

`OPENAI_MODEL` defaults to `gpt-5-mini` (`backend/config/settings.py:153`),
and the gpt-5 family rejects every non-default `temperature` value. The
LLM call at `backend/services/answer_script_service.py:348` passed
`temperature=0`, so every question hit this 400 inside the per-Q
try/except. The handler logged at warning level without `exc_info`, so
the real cause was invisible in the logs — the only artifact was the
"[Answer generation failed]" fallback the handler stamps onto the
question. Marks badge showed 0 because the doc was a list of plain
paragraphs and the badge's walker (`editor/toolbar.tsx:448-473`) only
counts `questionBlock`/`groupedQuestionBlock` nodes.

### Regression vs new failure

NEW failure, not a regression of the earlier "answer-script 500 /
IndentationError" round. The file imports cleanly (regression test
`test_module_imports_cleanly` still passes). The failure was introduced
at the file's birth (commit `9b2287b`, when `answer_script_service.py`
was first added) — the `temperature=0` was wrong from day one but only
became visible after the project's default model rolled forward to a
gpt-5 family model.

### Fix (commit `c51207a`)

`backend/services/answer_script_service.py:336-349`:
- Drop the `temperature=0` kwarg entirely so the API uses the default (1).
  Compatible with both gpt-5 family and older models.
- Upgrade the per-Q failure log from `logger.warning(..., exc)` to
  `logger.error(..., exc, exc_info=True)` so a future regression is
  never silent again.

`backend/services/answer_script_service.py:_build_answer_script_content`:
- Restructure the answer doc to emit `questionBlock` nodes per answer
  instead of plain paragraphs with embedded `[N M]` text. The editor's
  marks badge now counts the answer-script's question blocks, so the
  badge is no longer perma-zero.

`backend/q_instructions/tests/test_paper_plan_fixes.py`:
- `test_request_completion_does_not_send_unsupported_temperature` —
  monkey-patches the OpenAI client, runs `_generate_single_answer_llm_only`,
  and asserts the captured kwargs do NOT contain `temperature`. A future
  edit that puts back `temperature=0` (or any non-default) trips this.
- `test_build_answer_script_emits_question_blocks` — asserts the answer
  doc emits `questionBlock` nodes with the right `marks`/`number` attrs
  and that OR-answers expand into extra paragraphs inside the same block.

### Verification

End-to-end smoke against the live API (via a one-off repro script,
deleted after use):

```
Q1:
  marks=3
  answer=1. Photosynthesis is the process by which green plants, algae and
some bacteria use light energy to synthesize glucose from carbon dioxide
and water.
2. It occurs in chloroplasts containing chlorophyll …
✓ Answer generation works
```

Per-Q isolation: untouched. The `try/except` still wraps each question's
LLM call, so a single hard failure (model returns gibberish, network
hangs past the SDK timeout, etc.) still becomes a per-Q
"[Answer generation failed]" without blanket-failing the script.

### Blast radius

`_generate_single_answer_llm_only` only. Other LLM call sites:
- `services/openai_service.generate_answer_key` — never sent
  `temperature` (no change needed).
- `services/openai_service.caption_image_for_embedding` — same.
- `services/generation_service.py:968` — passes a `temperature: 0.7`
  inside a dict to `provider.stream_chat(llm_request)`, but the
  `OpenAIProvider.stream_chat` adapter at
  `apps/question_generation/infrastructure/providers/openai_provider.py:24`
  reads only `request.model/messages/response_format` and silently drops
  the dict's temperature. So that path is unaffected (temperature
  defaults to 1; gpt-5 accepts that). I left this dict-vs-LLMRequest
  shape mismatch alone for this PR — it's outside the answer-script
  scope and the GIM stream actually exercises a different normalised
  path. Flagged for a follow-up.

---

## CLUSTER B — intermittent figures + "Question visual" placeholder

### Why some figures succeeded and others didn't

The backend figure pipeline has TWO image-emitting paths:

1. **Inline-SVG figures** (`_figure_to_data_url`): validates the model's
   `figure: {type:"svg", content:"<svg…>"}`, enforces max 16 KB, rejects
   `<script>` / `<foreignObject>` / external `xlink:href`, and encodes
   the result as `data:image/svg+xml;base64,…`. These data URLs render
   anywhere, no network fetch needed.

2. **Source-image URLs** (`_allowed_image_urls`): for slots that have
   `requires_image=True` and the model cited an `image_url` that
   actually matches one of the chunks' image URLs (or, on retry, the
   fallback `image_url = allowed_urls[0]`). These come from
   `default_storage.url()` for an extracted PDF image, e.g.
   `/media/pdf_images/<pdf_id>/page-3-image-2.png`. They're **relative**
   paths — `AOS_PUBLIC_MEDIA_BASE_URL` is unset in dev, so
   `_public_media_url(stored_path)` returns `/media/...` directly
   (`services/document_service.py:27-32`).

The intermittence is per-question: a question whose figure path was (1)
got a working data URL; a question whose figure path was (2) got a
relative `/media/...` URL.

In **dev** (Next at :3000, Django at :8000), the browser resolves
`/media/...` against :3000, gets a 404, and shows the `<img>` alt text in
the broken-image icon — which is exactly where the literal
`alt: "Question visual"` (the brief's "surviving path") was hard-coded
in `frontend/components/tiptap-editor.tsx:1257` and `:1346`. In
**prod** the same path is silent IFF there is an nginx (or equivalent)
proxy routing `/media/` to Django; without it, the same 404 reaches
the browser.

The literal `alt="Question visual"` was last added in commit `b4e4023`
("centralize question generation planning") and never replaced — the
prior Cluster B work fixed the backend half (stop emitting hallucinated
URLs) but the frontend insertion sites still hard-coded the placeholder
alt and never resolved relative paths.

### Fix (commit `e6afc5b`)

`frontend/components/editor/extensions/float-image.tsx`:
- New `resolveFigureSrc(src)` helper. Returns `src` as-is for
  `data:`, `http://`, `https://`, and `blob:` URLs; for any other
  leading-slash path, prefixes `NEXT_PUBLIC_API_BASE_URL` (Django
  origin, default `http://localhost:8000`). Used in both the React
  NodeView render and the static `renderHTML` so the live editor, the
  PDF export (html2canvas captures the DOM), and any copy-paste-out
  path agree. Old saved papers with `/media/...` srcs now render
  correctly without a data migration.

`frontend/components/tiptap-editor.tsx`:
- Extract `buildFigureNode(imageUrl)` helper. Returns `null` for empty,
  "null"/"undefined" string literals, or any URL that isn't `data:`,
  `http(s)://`, or a leading-slash path. Otherwise returns a `floatImage`
  node with `alt: ""` (the previous literal `"Question visual"` was the
  exact text shown in the broken-image icon every time a relative path
  failed to load — eradicated).
- Both insertion sites (`questionsToAppend` and `sectionsToAppend`)
  route through this helper, so generation, review-tray insert, and
  any future call site share the same insertion guard + alt policy.

### Cluster B verification matrix

| Acceptance criterion | Status |
|---|---|
| Inline-SVG figures still render | ✓ (no backend change; FloatImage NodeView returns `data:` src unchanged) |
| Source-image URLs render in dev | ✓ (`resolveFigureSrc` prefixes Django origin) |
| Source-image URLs render in prod | ✓ (absolute URLs and `data:` URLs are pass-through; no change to existing prod proxy setups) |
| `<img alt="Question visual">` eradicated | ✓ (both insertion sites now route through `buildFigureNode`; only the historical comment string remains in source) |
| Text-self-contained fallback when figure can't be generated | ✓ (backend `_strip_figure_references` retry path is unchanged; FE `buildFigureNode` returns null instead of inserting a dead img) |
| Editor render | ✓ (FloatImage NodeView resolves src at render time, so old saved papers benefit too) |
| PDF export | ✓ (html2canvas captures the live DOM; with resolved URLs the img loads and is captured) |
| DOCX export | n/a (DOCX export does not handle images — pre-existing limitation noted in project memory) |

### Blast radius

Figure rendering only. No backend schema change, no data migration. The
`buildFigureNode` guard is strictly *more conservative* than the previous
unconditional insertion: it only DROPS imgs it would otherwise have
inserted as broken. Cluster B regression tests still pass
(`FigurePipelineTests` — `test_valid_inline_svg_becomes_data_url`,
`test_svg_with_script_is_rejected`, `test_oversized_svg_is_rejected`,
`test_coerce_question_rejects_figure_reference_without_figure`,
`test_coerce_question_accepts_figure_reference_with_inline_svg`).

---

## CLUSTER C — app-wide slowness

### Measurements (production build)

```
$ rm -rf .next && next build
✓ Compiled successfully in 7.0s
```

Bundle sizes (sum of all chunks emitted for each route's
`page_client-reference-manifest.js`):

| Route | Raw | Gzipped | TipTap chunk loaded? |
|-------|------:|---------:|---------------------|
| `/editor` | 2.42 MB | **704 KB** | yes (1.84 MB / 542 KB chunk) |
| `/dashboard` | 377 KB | 114 KB | no |
| `/paper-library` | ~390 KB | ~119 KB | no |
| `/question-bank` | ~385 KB | ~118 KB | no |
| `/settings` | ~387 KB | ~118 KB | no |

The 1.84 MB TipTap chunk is editor-route-only — Next 16's per-route
code-split already keeps it off the dashboard / library / question-bank
/ settings pages. So "next/dynamic split so non-editor routes don't pay
for TipTap" is a no-op here — they already don't pay. The bundle
**isn't** the cause of "opening anything is slow."

### Root cause (the brief's TOP suspect was right)

`(dashboard)/layout.tsx` wraps every protected route in `<ProtectedLayout>`,
which gates `children` on `useSession()`:

```ts
// frontend/lib/auth-client.ts — pre-fix
const [data, setData] = useState<SessionData | null>(null);
const [isLoading, setIsLoading] = useState(true);
…
useEffect(() => { fetchSession(); }, [fetchSession]);
```

Even though `loadSession()` returns synchronously when the module-level
cache (`sessionLoaded`, `cachedSession`) is hot, `useState` initialized
`data=null, isLoading=true`, the effect fired, `fetchSession` was
invoked, and an extra render flipped `isLoading=false` after the cache
hit. So every protected-route navigation paid:

- 1 wasted render with `data=null, isLoading=true` → ProtectedLayout
  rendered the centred spinner (Loader2 only, no shell)
- 1 microtask later, the cached session resolved → re-render with
  children

On a **cold load** (first nav since browser opened, or hard refresh),
the cost was much worse: `loadSession()` made a real HTTP round-trip
to `/api/auth/profile`, blocking the whole layout subtree on the
network (typically 80-500 ms; up to the 8 s `SESSION_TIMEOUT_MS`).

This is the brief's "every protected route gates on a session HTTP
round-trip" pattern, confirmed.

### Fix (commit `477d3d5`)

**(1) `useSession` initializes from the module cache synchronously.**

```ts
// frontend/lib/auth-client.ts — post-fix
const [data, setData] = useState<SessionData | null>(
  sessionLoaded ? cachedSession : null,
);
const [isLoading, setIsLoading] = useState(!sessionLoaded);
…
useEffect(() => {
  if (sessionLoaded) return;  // cache hit → skip the HTTP call entirely
  fetchSession();
}, [fetchSession]);
```

After the first session load anywhere in the app's lifetime, every
subsequent navigation renders children on the FIRST render — no
spinner flash, no extra render cycle, no second HTTP call.

**(2) `ProtectedLayout` renders shell optimistically when a refresh
token is present.**

```ts
const [hasRefreshToken, setHasRefreshToken] = useState(false);
useEffect(() => { setHasRefreshToken(Boolean(getRefreshToken())); }, []);
…
if (data?.user) return <>{children}</>;                // cache hit
if (isLoading && !timedOut && hasRefreshToken) return <>{children}</>;
if (isLoading && !timedOut) return <Spinner />;
return <Spinner />;  // session check failed and no token → redirect via effect
```

A refresh token in localStorage means "this device has logged in
before." We render the dashboard chrome immediately and let `useSession`
verify in the background. If verification fails (the 8 s timeout fires,
or `data?.user` is still falsy when `isLoading` flips), the existing
redirect-to-/login effect fires.

### Before/after (per-phase ms)

Measured render-path counts, not stopwatch ms — but the dominant
network-bound cost on cold load is `/api/auth/profile` (80-500 ms RTT
in dev; SDK timeout 8 s), and the dominant compute cost on warm nav is
React's render of a spinner-only subtree followed by the children
subtree.

| Phase | Before | After |
|---|---|---|
| Cold load (no cache, no token) | 1 spinner render → HTTP profile call → 1 children render | unchanged (this is the legit unauthenticated path) |
| Cold load (no cache, refresh token in localStorage) | 1 spinner render → blocking HTTP profile → 1 children render | 1 hydration spinner frame → effect fires → 1 children render; HTTP runs in background |
| Warm nav (cache hot) | 1 spinner render → 1 children render (extra render cycle, perceptible flicker) | 1 children render (no spinner, no flicker) |
| Hard refresh (cache cold, token present) | blocking HTTP profile → 1 children render | 1 hydration spinner frame → 1 children render; HTTP runs in background |

For the dominant case (warm internal nav), the saved cost is one full
ProtectedLayout subtree render and the perceptible spinner flicker.
For cold load with a token, the saved cost is the entire HTTP round-trip
on the critical path.

### Items NOT changed in Cluster C (with reasoning)

1. **next/dynamic split of TipTap on /editor.** Brief listed this as
   a candidate. Bundle measurement above shows it would not help
   "opening anything is slow" — TipTap is already editor-route-only.
   On /editor itself, splitting just rearranges the loading order:
   the user is on /editor specifically to use the editor, so the chunk
   has to load before they can do anything meaningful. Net latency win
   ≈ zero. Skipped.

2. **Figure externalization (base64 SVGs inline → external storage).**
   Project-memory note flags this as "unfinished work." The prior perf
   pass already de-coupled per-keystroke cost from figure-blob size
   (Fix A in the previous FIX_REPORT: stopped serializing the doc on
   every keystroke). So this only affects IDB read/write cost on
   figure-heavy paper load, not typing latency or per-nav perceived
   slowness. Bigger architectural change (backend SSE shape, TipTap
   floatImage `src` storage, IDB schema, PDF + DOCX exporters,
   migration for existing papers) — not in scope for this PR.

3. **GIM dict-vs-LLMRequest shape mismatch in
   `generation_service.py:964-972`.** Noted under Cluster A blast
   radius. Real bug, but out of scope here.

---

## Anti-regression sweep

Searched for the same anti-patterns elsewhere:

- `temperature\s*=` / `temperature\s*:` in `backend/` — only call site
  was `answer_script_service.py:348` (fixed) and the test file
  (intentional, asserts the absence). `test_llm.py` is a manual repro
  script; not part of automated tests. `generation_service.py:968` is
  the GIM dict path documented above.
- `"Question visual"` in `frontend/` — only the historical comment
  remains, no live emission paths.
- Blocking `useSession()` + spinner gate — only ProtectedLayout uses
  this pattern; no other layout in the app gates on a session check.
- Per-keystroke serialize + Zustand emit (the previous round's Cluster
  C subject) — untouched, still debounced via `debouncedLiveSync`
  every 1 s.
- StatusBar full-doc walk on `saveState` flip — untouched, still 500 ms
  debounce.
- Toolbar marks total recount — untouched, still 400 ms debounce.

## Test results

| Suite | Passed | Failed |
|---|---|---|
| `q_instructions/tests/` | 95 | 0 |
| Frontend `tsc --noEmit` | ✓ | — |
| Frontend `next build` (prod) | ✓ | — |
