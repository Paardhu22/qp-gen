# FIX_REPORT — Answer-script generation, intermittent figures, app-wide slowness, UI cleanup

Six fixes across four rounds. 98/98 backend tests pass; frontend
`tsc --noEmit` clean; production build succeeds (Next 16.2.6 Turbopack).

Commits (newest → oldest):
- `9a1c447` fix(ui): full subject labels in dropdown + remove ICSE option
- `be7ae3b` fix(export-docx): render floatImage figures in DOCX + doc env knobs
- `8b0e99c` fix(answer-script): allocate enough completion-token budget for reasoning
- `477d3d5` perf(auth): non-blocking session check on every protected-route nav
- `e6afc5b` fix(figures): resolve relative /media/ URLs + eradicate Question-visual alt
- `c51207a` fix(answer-script): remove unsupported temperature=0 + emit questionBlock nodes

No regressions to: OR-group A1/A2/grouped-OR, literal "1." typing,
per-keystroke save, StatusBar / marks debounces, Cluster B
"Question visual" backend rejection, the useSession cache fix from
round 1.

---

## ROUND 2 — what landed in this round

The previous report covered rounds 0 + 1. The current round closed the
last three gaps the user flagged:

1. **Answer script still placeholdered most Qs** — the temperature
   fix made the API call succeed, but for any answer that needed real
   reasoning headroom the LLM ate the entire token budget on internal
   reasoning and returned empty content (commit `8b0e99c`). Detailed
   below under "CLUSTER A — round 2".
2. **Cluster B media-origin verification** — confirmed the FE resolver
   is already env-driven (`NEXT_PUBLIC_API_BASE_URL`) and the BE
   `_public_media_url` already supports `AOS_PUBLIC_MEDIA_BASE_URL`.
   Tightened the doc-comment in `float-image.tsx` so the prod deploy
   story is unambiguous (commit `be7ae3b`). No behavior change.
3. **Figures survive DOCX export** — round 1 fixed editor + PDF but
   DOCX silently dropped every figure. Now embeds inline-SVG (as
   `ImageRun({type:"svg",fallback})`) and /media source images (as
   PNG/JPEG `ImageRun`s) via async figure resolution after the parser
   walk (commit `be7ae3b`). PDF was already correct — html2canvas
   captures the live DOM, which renders through `resolveFigureSrc`.

Test count went 95 → 98 (3 new regression tests under
`AnswerScriptServiceTests`).

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

## CLUSTER A — round 2 (commit `8b0e99c`)

After the round-1 `temperature=0` fix removed the BadRequestError, the
generator no longer crashed but most questions still rendered as
"[Answer to be filled by teacher]" — Q29-Q38 of a 38-question paper all
empty while Q28 (and a few others) had full worked solutions.

### Real cause (measured against the live API)

A standalone repro hit the exact API call with `_build_user_prompt` and
varied `max_completion_tokens`. The 5-mark long-answer prompt produced:

| `max_completion_tokens` | `finish_reason` | `completion_tokens` | `reasoning_tokens` | visible chars |
|------:|---|------:|------:|------:|
|  1000 | **`length`** |  1000 | **1000 (all of it)** | **0** |
|  2000 | `stop`   |  1091 |  768 | 1486 |
|  4000 | `stop`   |   878 |  576 | 1350 |
|  8000 | `stop`   |  1114 |  832 | 1296 |

So gpt-5-mini's default reasoning effort burned all 1000 tokens on
internal reasoning, left 0 for visible output, and returned
`finish_reason="length"` with empty content. `_parse_answer_payload("")`
returns None; `_fallback_answer_from_text("", ...)` extracts nothing
either; the per-Q handler stamped the empty answer through to
`_build_answer_script_content` where the `or "[Answer to be filled by
teacher]"` safety net kicked in. Q28 worked because either its prompt
was shorter or it happened to fit inside 1000 reasoning tokens — a
function of the model's internal heuristics, not anything the service
controls.

### Distinguishing "couldn't generate" from "intentionally subjective"

The string `"[Answer to be filled by teacher]"` is misleading when the
real cause is a programmatic failure. All five emission sites now use
`"[Answer generation failed]"` instead — five sites in
`answer_script_service.py`, plus the parser-fallback OR branch in
`_fallback_answer_from_text`. There is currently no path in the
service that marks a Q as genuinely subjective; if a future flag is
added, the teacher-fills wording can be reintroduced there
orthogonally.

### Fix

`backend/services/answer_script_service.py`:
- Add `reasoning_effort="low"` (gated on
  `OPENAI_MODEL.startswith(("gpt-5","o1","o3"))` so a future swap to a
  non-reasoning model can't 400 on an unsupported kwarg). For this
  factual marking-scheme task, "low" cuts reasoning-token spend
  ~10× without affecting answer quality (the model still reasons
  enough to apply the marking-scheme format rules).
- Raise default `max_completion_tokens` 1000 → 4000.
- Detect `finish_reason="length"` or empty content on the FIRST
  attempt and immediately retry with 8000 tokens — independent of the
  existing invalid-JSON retry path (which itself now uses 8000). A
  truncated response can't be parsed, but the remedy is more budget,
  not "your JSON was bad".

### Regression tests (95 → 98)

`backend/q_instructions/tests/test_paper_plan_fixes.py`:
- `test_per_q_budget_is_sufficient_for_reasoning_models` — captures
  the kwargs the service would pass to OpenAI, asserts
  `max_completion_tokens ≥ 4000` AND `reasoning_effort` is present for
  gpt-5 / o1 / o3 family.
- `test_truncated_first_attempt_triggers_higher_budget_retry` —
  mocks a length-truncated first response and asserts the retry sends
  a STRICTLY larger budget AND that the recovered answer is the real
  text (not the failure placeholder).
- `test_thirty_question_paper_has_no_placeholder_answers` — drives the
  per-Q pipeline 30 times (matching the production symptom of Q29-Q38
  all empty) and asserts every answer is real, never the teacher
  placeholder.

### Live-API smoke verification

Re-ran a 4-question batch with the new defaults against the live API:

```
Q1 marks=5 LONG_ANSWER  → len=1383  ✓ real answer (Newton's laws)
Q2 marks=3 SHORT_ANSWER → len=359   ✓ real answer (conservation of energy)
Q3 marks=2 SHORT_ANSWER → len=504   ✓ real answer (mass vs weight)
Q4 marks=5 LONG_ANSWER  → len=1107  ✓ real answer (Ohm's law)
```

Per-Q isolation preserved: a single Q hitting a genuine API failure
(e.g. content moderation block) still stamps `[Answer generation
failed]` for that one Q and the other 37 succeed.

### Blast radius

`_generate_single_answer_llm_only` only. Other LLM call sites
(`openai_service.generate_answer_key`, `openai_service.caption_image_for_embedding`,
`generation_service.stream_chat`) don't pass `max_completion_tokens`
and let the API default — they're unaffected by the budget change. The
`reasoning_effort` kwarg is gated by model-name prefix so a non-gpt-5
model doesn't 400. The "[Answer generation failed]" rename is purely
display — no callers branch on the exact placeholder text.

---

## CLUSTER B — round 2 verification (no code change)

Confirmed the round-1 `resolveFigureSrc` is env-driven, not hardcoded:

```ts
// frontend/components/editor/extensions/float-image.tsx
const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
```

The `localhost:8000` literal is the dev fallback (matches
`lib/api-client.ts:API_BASE_URL` for consistency — if api-client can
talk to Django, the figure resolver can too).

The backend side is also already env-driven:

```py
# backend/services/document_service.py:_public_media_url
public_base = getattr(settings, "AOS_PUBLIC_MEDIA_BASE_URL", "")
if public_base:
    return f"{public_base}{media_url if media_url.startswith('/') else '/' + media_url}"
return media_url
```

So there are TWO independent prod knobs and you only need ONE:

- Set `AOS_PUBLIC_MEDIA_BASE_URL` on the BE — `default_storage.url()`
  returns absolute URLs up front, the persisted doc is portable across
  origins, FE doesn't have to resolve at render time. **Preferred for
  prod.**
- Set `NEXT_PUBLIC_API_BASE_URL` on the FE — `resolveFigureSrc`
  prefixes any leading-slash src at render time. Useful when the FE
  and BE live on different origins (Next dev :3000 + Django :8000).

If both are unset, source-image URLs stay relative and only render
when FE+BE share an origin (typical for an nginx-proxied prod where
`/media/` routes to Django from the same host).

The round-2 change is doc-only — the comment block in `float-image.tsx`
now spells this out so future deploys can pick the right knob without
re-reading the source.

---

## CLUSTER C — round 2 (commit `be7ae3b`)

The round-1 fix landed in `FloatImage`'s NodeView (editor) and
`renderHTML` (PDF). The DOCX exporter was a separate codepath that
WAS NOT touched, so figures vanished from .docx files even though they
rendered in the editor and in the PDF.

### Verification matrix

| Surface | Round 1 status | Round 2 status |
|---|---|---|
| Editor live render | ✓ FloatImage NodeView resolves via `resolveFigureSrc` | unchanged |
| PDF export (html2canvas → jsPDF) | ✓ captures the live DOM, including resolved imgs | unchanged. CORS verified — `curl -H "Origin:" /media/...` returns `access-control-allow-origin: http://localhost:3000` + `Access-Control-Allow-Credentials: true`, so `html2canvas({useCORS:true})` can taintlessly draw both inline-SVG data URLs and cross-origin source images. |
| DOCX export (custom HTML→DOCX walker) | **broken** — no `floatImage` branch at all | **fixed** — figures embedded as `ImageRun` |

### DOCX figure pipeline

`frontend/lib/export-docx.ts`:
- The synchronous walk reserves a placeholder `Paragraph` slot for
  each `floatImage` node it encounters and pushes a `FigureTask` with
  `{sentinelIndex, src, width, height}`.
- After the walk completes, `Promise.all` resolves every figure in
  parallel via `loadFigureBytes`:
  - `data:` URLs (the inline-SVG figure pipeline) — base64-decoded
    in-process; SVG is rasterized to PNG via canvas at 2× supersample
    and wrapped in `ImageRun({type:"svg", fallback:{type:"png"}})`
    so Word renders the vector but older clients still see the PNG.
  - `/media/...` URLs (real PDF page images) — fetched through
    `resolveFigureSrc` so the request hits Django, not the FE origin.
    `mode:"cors"`, `credentials:"include"` — Django's CORS headers
    (verified above) let the response back into the page; the blob's
    MIME type drives the `ImageRun` kind.
- Each successfully-loaded figure replaces its placeholder
  `Paragraph` at the reserved index. Failed loads (CORS denied, 404,
  malformed bytes) leave the empty placeholder so the surrounding
  question stem still surfaces — matches the backend's
  "text-self-contained fallback" contract.

### Blast radius

DOCX export only. No backend / schema change. The synchronous walk
is unchanged for all non-figure nodes, so questions / sections /
instructions / tables / paper-header are byte-identical to the
round-1 output. The async figure resolution happens AFTER the walk,
so a single slow / failing fetch can't reorder unrelated DOCX content
— each figure is sliced into its reserved slot or replaced with the
empty placeholder. No new dependencies; `ImageRun` was already in the
`docx` npm package, just unused.

---

## ROUND 3 — UI cleanup + ICSE removal (commit `9a1c447`)

Two small UI fixes shipped ahead of the q_instructions audit:

### Subject dropdown truncation

`generator-form.tsx` placed Board / Class / Subject in a 3-column grid
(`grid-cols-3 gap-4`). In a typical resizable sidebar (~480 px wide),
each column got ~150 px — not enough for the longest subject label
("English Language & Literature (Code 184)" ≈ 290 px at the current
font).

Two compounding issues:

1. The open dropdown popup defaulted to `w-(--anchor-width)` (Base UI's
   CSS variable for the trigger width), so the list was clamped to the
   same ~150 px and truncated every item to "Mathematics Standard (",
   "English Language & Liter", etc. Fixed by changing the Select
   component's default popup class from `w-(--anchor-width)` to
   `min-w-(--anchor-width) w-max max-w-[min(36rem,calc(100vw-1rem))]`
   — at least as wide as the trigger, grows to the longest item, capped
   at 36rem / viewport width.
2. The trigger itself still truncated the selected value because the
   column was too narrow. Restructured the layout: Board + Class share
   one row (now `grid-cols-2 gap-4`), Subject is on its own row at full
   sidebar width.

### ICSE removal

The Board dropdown previously offered `CBSE` and `ICSE`. The product is
CBSE-only — the routing gate in
`services/generation_router.py::should_use_new_engine` already requires
`board == "CBSE"`, and no live code branches on `Board.ICSE`. Removed
all dead ICSE config:

| File | Change |
|---|---|
| `frontend/components/generator-form.tsx` | drop `<SelectItem value="ICSE">` |
| `frontend/app/(dashboard)/dashboard/page.tsx` | drop the "(CBSE, ICSE, custom templates)" caption |
| `backend/q_instructions/core/enums.py` | remove `EducationBoard.ICSE` enum entry |
| `backend/apps/question_generation/domain/enums.py` | same (duplicate enum file) |
| `backend/q_instructions/core/constants.py` | remove `ICSE_TOTAL_MARKS`, `ICSE_EXAM_DURATION_MINUTES`, `ICSE_ALLOW_FRACTIONAL_MARKS` (verified unimported) |
| `backend/apps/question_generation/domain/constants.py` | same (duplicate constants file) |

Left intentionally:

- The `"ICSE"` STRING in `test_hybrid_routing.test_should_use_new_engine_ineligible`
  — it's a generic "non-CBSE input" test fixture asserting the router
  rejects any value that isn't "CBSE". Removing the UI option doesn't
  weaken that assertion.
- `q_instructions/legacy/*` files that reference ICSE — explicitly
  marked legacy, no live consumer. Cleanup belongs to a future
  legacy-removal pass.

Blast radius: routing only. `should_use_new_engine` already required
`board == "CBSE"` for any active engine routing, so even if a stale
paper or external caller smuggles in `"ICSE"`, it falls through to the
same "not configured" error path it always did. 98/98 backend tests
pass; `tsc --noEmit` clean.

---

## ROUND 3.5 — q_instructions Phase 1 audit

Deliverable: `Q_INSTRUCTIONS_AUDIT.md` (read-only, no code modified in
this phase). It traces the LIVE streaming generation path, flags every
dead and duplicated blueprint module, maps the validation / routing /
schema architecture, lists hard-coded constants that should be config,
and provides a per-subject blueprint inventory pinned by the existing
test suite.

Key finding (confirms the brief's hypothesis): for the default Board
Mode / Class 10 / exact-CBSE path, **every** subject's blueprint comes
from inline functions in `services/generation_router.py`
(`_exact_class10_blueprint_entries_{mathematics,english,hindi,telugu}`
plus inline literals for science / social science). The
`q_instructions/subjects/*/blueprint.py` registries and
`q_instructions/subjects/{mathematics,english,hindi,telugu}/orchestrator.py`
files are dead for streaming — they have no non-self imports anywhere
in the live codebase. Only `subjects/{science,social_science}/orchestrator.py`
are used, and only on the secondary "custom count" branch.

Phase 2 (CBSE SQP fact-check) is gated on the user reviewing this
audit and providing the official `cbseacademic.nic.in` SQP +
marking-scheme PDFs per subject. The audit lists the exact PDFs
needed and flags Telugu (089) as the subject most likely to need a
fallback authoritative source.

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
- `"[Answer to be filled by teacher]"` — eradicated; every empty-answer
  surface now stamps `"[Answer generation failed]"` instead. Reserves
  the teacher-fill wording for a future explicit-subjective flag.
- `max_completion_tokens` / `max_tokens` in `backend/services/` — the
  answer-script path is the only one that capped output. Generation /
  caption / generate_answer_key paths let the API default.
- `reasoning_effort` — only set in the answer-script path (gated on
  gpt-5/o1/o3 model prefix). No other service uses it.
- Figure-bearing nodes in the editor have ONE NodeView (`floatImage`)
  and ONE export-time consumer per surface (FloatImage NodeView for
  editor render, html2canvas for PDF, `CustomHtmlToDocxParser` for
  DOCX). All three resolve through `resolveFigureSrc`.
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
| `q_instructions/tests/` | 98 | 0 |
| Frontend `tsc --noEmit` | ✓ | — |
| Frontend `next build` (prod) | ✓ | — |
