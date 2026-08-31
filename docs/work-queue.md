# QP-Gen Work Queue

*Assembled 2026-08-30 at `main@5996aa4`, updated as items ship, from the three audits: [visual/motion](./ui-audit-and-animation-playbook.md), [guidance](./ux-guidance-audit.md), [feature](./feature-audit.md). One ordered list, so there is a single place to pick from.*

**Ordering principle:** broken → lost → confusing → missing → inconsistent → polish. A feature a teacher cannot reach outranks a feature that looks wrong, which outranks a feature that is merely absent.

Effort figures are from the source audits unless re-verified here; anything re-verified says so.

---

## Tier 0 — Broken now  ✅ CLEARED

Things that do not work, or work wrongly, in the shipped product.

| # | What | Effort | Source | Evidence |
|---|---|---|---|---|
| ~~0.1~~ ✅ | **Sets B/C unreachable below 1024px.** Outline hides in both states; the set tabs live only inside it | ~1 hr | Guidance Gap 9 | `document-outline.tsx:178, 193, 216` |
| ~~0.2~~ ✅ | **White-on-sand CTAs in dark mode**, ~1.7:1 contrast on 7 primary buttons | ~15 min | Visual #9 | 7 sites, 4 files — verified all on `bg-primary` |
| ~~0.3~~ ✅ | **Export S3 backup 404s silently** from the URL-param path | ~10 min | Feature Overlap 2 | `editor/page.tsx:412` vs the fixed `toolbar.tsx:826` |
| ~~0.4~~ ✅ | **`animate-shake` does not exist** — "Sync failed" is the only sync state that never animates | ~15 min | Visual #17 | `tiptap-editor.tsx:382`; 0 keyframe definitions anywhere |

**Tier 0 total: ~1 hr 40 min. All four shipped** on `fix/tier0-quick-fixes`.

---

## Tier 1 — Quick wins  ✅ CLEARED

Small, high value, low risk. Any of these is a clean standalone commit.

| # | What | Effort | Source | Note |
|---|---|---|---|---|
| ~~1.1~~ ✅ | Editor opens with one panel, not two | ~5 min | Guidance | One line (`editor/page.tsx:232`). Re-verified as safe standalone — the collapsed rail still renders at `lg:` |
| ~~1.2~~ ✅ | Delete 5 dead components (~490 LOC) | ~15 min | Feature | `file-upload`, `drawing-node`, `template-picker`, `tiptap-viewer`, `ui/cloud-watch-form`. Zero static **and** dynamic importers |
| ~~1.3~~ ✅ | Empty-state CTA buttons ×3 | ~1.5 hr | Guidance Gap 1 | Copy already written; the button pattern exists 3 lines away in each file |
| ~~1.4~~ ✅ | Route rename so URLs match nav labels | ~1 hr | Guidance Gap 6 | Needs redirects. Independent of everything |
| ~~1.5~~ ✅ | Signal the off-screen Actions column | ~1 hr | Guidance Gap 11 | Admin-only reach |
| ~~1.6~~ ✅ | Blueprint step dots below `sm` | ~45 min | Guidance Gap 10 | Restores the file's own stated intent |

All six shipped on `fix/tier0-quick-fixes`. Note 1.4 landed as `/questions` and `/papers`, not `/question-bank` and `/papers` as originally written — moving `/paper-library` onto `/question-bank` would have put a permanent redirect on a live route and shadowed the page. Both old paths now redirect cleanly.

**Decision still open on 1.2:** `GiftOverlay` (396 LOC) and `GooeyNav` (224 LOC) are also unimported, but the visual audit proposes *wiring* them rather than deleting. They are excluded from 1.2 until you call it. Wire or delete — carrying them unwired is the only option with no upside.

---

## Tier 2 — Substantial, well-defined  ✅ CLEARED

Known scope, no open questions, 1–3 hours each.

| # | What | Effort | Source |
|---|---|---|---|
| ~~2.1~~ ✅ | First-run primitive (`useFirstRun`) | ~3 hr | Guidance Gap 2 — gates 2.2 and 2.6 |
| ~~2.2~~ ✅ | Editor blank state | ~3 hr | Guidance Gap 3 |
| ~~2.3~~ ✅ | Error recovery pass — 88 dead-end toasts | ~2.5 hr | Guidance Gap 4 |
| ~~2.4~~ ✅ | One export hook for PDF + DOCX | ~2 hr | Feature — supersedes 0.3, do 0.3 first anyway |
| ~~2.5~~ ✅ | Merge the two diverged `Grainient` copies | ~1.5 hr | Feature Overlap 4 — 180 differing lines |
| ~~2.6~~ ✅ | State-aware dashboard suggestions | ~2 hr | Guidance Gap 5 |
| ~~2.7~~ ✅ | Unify the 8 page-title treatments | ~2 hr | Visual #15 — **blocks the display-typeface work** |
| ~~2.8~~ ✅ | Adopt the loading system already built | ~2.5 hr | Visual #18 — 14 raw `Loader2`, wrong skeleton on Templates, 3 blank auth fallbacks |
| ~~2.9~~ ✅ | `--success` / `--warning` tokens, retire 71 hardcoded colour utilities | ~3 hr | Visual #10 |
| ~~2.10~~ ✅ | Dark-mode treatment for the A4 sheet | ~1 hr | Visual #16 — see correction below |
| ~~2.11~~ ✅ | `TestScienceEngineView` → management command | ~1 hr | Feature — removes a routed LLM-spending endpoint |

Two corrections found while doing these. **2.9's premise was wrong**: `--success` and `--warning` already existed in `globals.css` for both themes and were already mapped in `@theme inline`; only adoption was missing, so it cost far less than the ~3 hr estimate and unblocked the work that depended on it immediately. **2.7 turned out to be the real blocker** for the display typeface — there was no heading scale to attach a face to, and now there is (`components/ui/page-title.tsx`), so 3.6 is unblocked.

**Correction on 2.10.** The visual audit states the A4 page "has no visible edge in dark mode." Re-verified: overstated. The sheet is hardcoded `#ffffff` (`editor.css:45`) against a darkened canvas (`globals.css:640`), so the edge is plainly visible by luminance. What is actually lost is the *lift* — `editor.css` has 0 `.dark` selectors in 1,361 lines, so the hairline `rgb(0 0 0 / 0.08)` border and the slate-tinted shadow stack (`:55-59`) both do nothing against dark. The file's own comment says the shadow is what makes the sheet "read as lifted rather than as drawn"; that intent is defeated. Real, but cosmetic — not Tier 0.

---

## Tier 3 — Larger or needs a decision first  (4 shipped, 1 withdrawn, 1 half)

| # | What | Effort | Note |
|---|---|---|---|
| ~~3.1~~ ✗ | ~~Merge the two source pickers~~ | — | **Withdrawn — the premise was wrong.** See below |
| ~~3.2~~ ✅ | Share generation state between the two SSE consumers | ~2 hr | Reframed and shipped; **uncovered two live bugs** — see below |
| 3.3 ◐ | Consolidate 5 hand-rolled modals onto `Dialog` | ~4 hr | **Half done** (`658e939`): one scrim recipe and a documented z-index scale. The `Dialog` migration itself is not attempted — five different shapes, and focus traps are not verifiable without a browser |
| 3.4 | Motion phases: page transitions → stagger → list-detail morph | ~6 hr | Visual 6–9. Reduced-motion work gates these |
| ~~3.5~~ ✅ | Dashboard home state | ~3 hr | Shipped as recent-papers on the empty state — see note below |
| ~~3.6~~ ✅ | Display typeface | ~1 hr | Playfair, scoped to page identity. 2.7 was the unblocker |
| 3.7 | Tooltips on dense surfaces | ~2.5 hr | Deprioritised — see note below. First step is promoting the tooltip out of `ui/ai-prompt-box.tsx` into a primitive |
| 3.8 | Delete `/api/generation/answer-key` | ~30 min + verification | Evidence upgraded — it is a *superseded predecessor*, not merely unused. Still your call; see below |
| 3.9 | **Resolve the three-engine question** | days | Product decision, not a refactor. ~14,000 LOC hangs on it |

---

### 3.1 withdrawn — there is only one picker

The audit read two files that both mention sources and called them rivals.
They are not. `hsat-source-picker.tsx` browses the catalogue and starts an
ingest; `blueprint/source-panel.tsx` lists what is already attached and offers
the two ways to attach more. Its "Choose from the library" tile calls
`onOpenHsatPicker`, which lifts through `blueprint-modal.tsx:113` to the editor
page and opens the picker. **They compose.** A teacher does not meet two
interfaces; they meet a panel and the dialog that panel opens.

They shared `AppliedHsatSource` because one produces it and the other renders
it — correct, except for where it lived. Five modules were importing a domain
type out of a leaf dialog. Moved to `lib/hsat-source.ts` (`18058b6`). That is
the whole of what 3.1 was worth: ~15 minutes, not ~4 hours.

### 3.2 shipped, reframed — and it was hiding two bugs

Sharing the *state* was the wrong goal. The editor builds a document out of
this stream; the dashboard runs a printing-press animation over it. A common
reducer would have produced a shape wrong for both. What needed sharing was
what the events **mean**, and that had already drifted.

The backend emits 13 event types on `/api/generation/questions/stream`. The
editor handled 12. The dashboard handled 9 — dropping `saved`, `notice` and
`warning` on the floor. The last two are the pool pipeline's only channel for
telling a teacher something went sideways but was recovered; on the chat path
they went nowhere at all.

`lib/generation-stream.ts` now holds the vocabulary — a union verified against
the backend rather than against either client, a decoder that cannot throw, and
`handleAmbientEvent` for the events whose right response is identical
everywhere. Both consumers read through it; state stays where it was.

**Bug 1 — every chat-path generation error read "Failed to parse stream
payload".** `readSseStream` wrapped the JSON parse and the handler dispatch in
one `try`. The dashboard's handler throws on an `error` event, which is how it
aborts the stream. So the throw was caught by the parse handler, re-entered
with the parse message, threw again from inside the catch, and reached the
teacher as a parse error. "No usable content in those chapters", the readiness
gate's rejection, a model timeout — all replaced, one frame after the real
reason arrived. Parse and dispatch are now separate.

**Bug 2 — the dashboard appended duplicate sets.** The editor always replaced
by label; the dashboard pushed. A re-emitted label put the same set on the
press twice and handed the editor two tabs of it.

Both in `4526520`.

### 3.8 — stronger evidence, still your call

The audit had it as "zero callers in this frontend, so check deployment logs
before removing." It is more clear-cut than that. `AnswerKeyView`
(`POST /api/generation/answer-key`) takes paper HTML, returns answer HTML, and
saves nothing. `AnswerScriptGenerateView`
(`POST /api/generation/papers/<id>/generate-answer-script/`) is the shipped
feature — called from `lib/api-client.ts:757`, used across `papers/page.tsx`,
backed by a 500-line service with retries and marking-scheme structure.

`generate_answer_key` has exactly one caller in the whole backend: the dead
view. So this is not an endpoint that happens to be unused — it is the
**superseded predecessor** of a feature that shipped. The frontend is the only
client, and it uses the successor.

Still not deleted, because deleting a routed endpoint is outward-facing and I
cannot read the deployment logs. But the question is narrower than it was:
not "does anything call this?" but "did anything ever call this that was not
our frontend?"

### A flag that was guarding nothing

Found while checking 3.8. `ENABLE_TEST_ENDPOINTS` existed for exactly one
route, which became a management command in 2.11 — so it had been gating
nothing since that commit. Removed (`a43e1e3`), which **closes the handoff's
loose end** about checking it on the host: there is no longer a value to check.

Same commit: `pool/model1.py:430` and `openai_service.py:129` both wrote
`getattr(settings, "<STAGE>_MODEL", settings.OPENAI_MODEL)` — the exact
inheritance `settings.py:337-343` forbids by name, at the call site the
prohibition exists to protect. Inert (settings always defines the stage
models), so nothing changes; fixed so the forbidden pattern stops living in
the code its prohibition is about.

---

**On 3.5.** Shipped as the part that fits the surface as it stands: the last three papers on the dashboard's empty state, below the prompt box. Deliberately *not* the full stats board the audit sketched — the chat is what that page is, and starting something new should stay the primary act on it.

**On 3.7 (tooltips).** Deprioritised rather than done. The audit ranked it weakest, and the premise is softer than it looked: the editor toolbar already carries 29 native `title=` attributes, so those controls are labelled — they are just labelled with slow, unstyled browser tooltips rather than the app's own. Worth doing eventually; not worth a 1400-line JSX rewrite ahead of the items below. Note there is no `components/ui/tooltip.tsx` — the only styled tooltip lives inside `ui/ai-prompt-box.tsx` on `@base-ui/react`, and promoting it to a primitive is the real first step.

---

## Suggested session shapes

**~40 minutes** — Tier 0 items 0.2, 0.3, 0.4. Three separate commits: an accessibility bug, a data bug, and a broken animation. Nothing depends on anything else.

**~2 hours** — the above plus 0.1 and 1.1. Ends with the editor no longer hiding a feature and no longer opening cramped. This is the highest-value two hours in the queue.

**~4 hours** — add 1.3 and 1.2. Every dead-end empty state becomes a door and ~490 lines leave the repo.

**Do not start after 10pm:** 1.4 (route rename — touches redirects and every internal link), 2.1–2.2 (needs design decisions), anything in Tier 3.

---

## What this queue does not decide

- **Wire or delete `GiftOverlay` / `GooeyNav`** — the visual and feature audits disagree by design. Yours to call.
- **The three-engine question (3.9)** — everything else in this file is small next to it.
- **Whether four paper-creation front doors is right** — flagged in the feature audit as a decision that accreted rather than one that was made.
