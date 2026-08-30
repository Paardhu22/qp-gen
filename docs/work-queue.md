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

## Tier 2 — Substantial, well-defined  (10 of 11 shipped)

Known scope, no open questions, 1–3 hours each.

| # | What | Effort | Source |
|---|---|---|---|
| ~~2.1~~ ✅ | First-run primitive (`useFirstRun`) | ~3 hr | Guidance Gap 2 — gates 2.2 and 2.6 |
| ~~2.2~~ ✅ | Editor blank state | ~3 hr | Guidance Gap 3 |
| 2.3 | Error recovery pass — 95 dead-end toasts | ~2.5 hr | Guidance Gap 4 |
| ~~2.4~~ ✅ | One export hook for PDF + DOCX | ~2 hr | Feature — supersedes 0.3, do 0.3 first anyway |
| ~~2.5~~ ✅ | Merge the two diverged `Grainient` copies | ~1.5 hr | Feature Overlap 4 — 180 differing lines |
| ~~2.6~~ ✅ | State-aware dashboard suggestions | ~2 hr | Guidance Gap 5 |
| ~~2.7~~ ✅ | Unify the 8 page-title treatments | ~2 hr | Visual #15 — **blocks the display-typeface work** |
| ~~2.8~~ ✅ | Adopt the loading system already built | ~2.5 hr | Visual #18 — 14 raw `Loader2`, wrong skeleton on Templates, 3 blank auth fallbacks |
| ~~2.9~~ ✅ | `--success` / `--warning` tokens, retire 71 hardcoded colour utilities | ~3 hr | Visual #10 |
| ~~2.10~~ ✅ | Dark-mode treatment for the A4 sheet | ~1 hr | Visual #16 — see correction below |
| ~~2.11~~ ✅ | `TestScienceEngineView` → management command | ~1 hr | Feature — removes a routed LLM-spending endpoint |

Remaining in Tier 2: **2.3 only** (error recovery — 95 dead-end toasts).

Two corrections found while doing these. **2.9's premise was wrong**: `--success` and `--warning` already existed in `globals.css` for both themes and were already mapped in `@theme inline`; only adoption was missing, so it cost far less than the ~3 hr estimate and unblocked the work that depended on it immediately. **2.7 turned out to be the real blocker** for the display typeface — there was no heading scale to attach a face to, and now there is (`components/ui/page-title.tsx`), so 3.6 is unblocked.

**Correction on 2.10.** The visual audit states the A4 page "has no visible edge in dark mode." Re-verified: overstated. The sheet is hardcoded `#ffffff` (`editor.css:45`) against a darkened canvas (`globals.css:640`), so the edge is plainly visible by luminance. What is actually lost is the *lift* — `editor.css` has 0 `.dark` selectors in 1,361 lines, so the hairline `rgb(0 0 0 / 0.08)` border and the slate-tinted shadow stack (`:55-59`) both do nothing against dark. The file's own comment says the shadow is what makes the sheet "read as lifted rather than as drawn"; that intent is defeated. Real, but cosmetic — not Tier 0.

---

## Tier 3 — Larger or needs a decision first

| # | What | Effort | Note |
|---|---|---|---|
| 3.1 | Merge the two source pickers | ~4 hr | Two live call sites; they already share a type |
| 3.2 | Share generation state between the two SSE consumers | ~4 hr | Transport is already shared; the state handling is not |
| 3.3 | Consolidate 5 hand-rolled modals onto `Dialog` | ~4 hr | Visual #12/#13 — 5 scrim recipes, 4 z-index escapes |
| 3.4 | Motion phases: page transitions → stagger → list-detail morph | ~6 hr | Visual 6–9. Reduced-motion work gates these |
| 3.5 | Dashboard home state | ~3 hr | Visual #5 / overlaps Guidance Gap 5 |
| 3.6 | Display typeface | ~1 hr | **Blocked by 2.7** |
| 3.7 | Tooltips on dense surfaces | ~2.5 hr | Weak until 2.2 lands |
| 3.8 | Delete `/api/generation/answer-key` | ~30 min + verification | Only proven unused by *this* frontend. Check deployment logs first |
| 3.9 | **Resolve the three-engine question** | days | Product decision, not a refactor. ~14,000 LOC hangs on it |

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
