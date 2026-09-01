# Session Handoff — 2026-08-31

**Branch:** `fix/tier0-quick-fixes` · **27 commits** · **not pushed** · base `main@5996aa4`

Nothing is half-finished. Every commit typechecks and lints clean, and the branch ends on a committed state. **None of it has been run in a browser** — that is the whole of what is left, and `docs/manual-test-checklist.md` is the list.

---

## What to do next, in order

1. **`npm install` in `frontend/`.** `recharts` is in `package.json:71` but missing from `node_modules`, so the admin usage page will not build. Pre-existing, not from this branch.
2. **Work `docs/manual-test-checklist.md`** — Batches 1, 2 and 3. Start with Batch 2's first item (Sets B/C below 1024px); it is the one that was actually broken for users.
3. **Two decisions are waiting on you** — see the bottom of this file.
4. Then pick up `docs/work-queue.md`, which has Tier 3 items 3.1–3.4 left.

---

## The five documents

| File | What it answers |
|---|---|
| `ui-audit-and-animation-playbook.md` | Visual, motion, design system |
| `ux-guidance-audit.md` | What the product tells a teacher, and layout that hides things |
| `feature-audit.md` | What it offers, and where it offers it twice |
| `work-queue.md` | One ordered list drawn from all three |
| `manual-test-checklist.md` | **What still needs a human** |

Kept separate on purpose. Mixing them makes each worse — the guidance doc kept finding things the visual doc had graded as "working".

---

## Progress

**Tier 0 (broken), Tier 1 (quick wins), Tier 2 (substantial): all cleared.** Tier 3: 3 of 9.

### The four that were genuinely broken
- **Sets B and C were unreachable below 1024px.** The document panel hid in both states and the set tabs live only inside it. Generated, saved and exported fine — just unreachable on a tablet.
- **Every URL-param export silently failed its cloud backup.** Local download succeeded, so the toast said "PDF downloaded!" and nothing landed.
- **Primary buttons were ~1.7:1 in dark mode** — white on sand across 7 CTAs.
- **`animate-shake` did not exist.** "Sync failed" was the one sync state that never moved.

### Everything else
Empty states got buttons · routes renamed to match their labels · editor blank state · first-run primitive · adaptive dashboard prompts + recent papers · one export path · Grainient copies merged · page titles on one scale · display typeface · loading system adopted · status colour tokens · error retry + one voice · A4 sheet in dark mode · one scrim recipe + documented z-index scale · engine test endpoint moved off the router · 5 dead components deleted (~824 lines).

---

## Three corrections to the audits

Worth knowing, because the audits are otherwise the source of truth:

1. **The `--success`/`--warning` tokens already existed.** The visual audit said they did not. They were defined for both themes and mapped in `@theme inline`; only adoption was missing. Corrected in the audit itself.
2. **"The A4 page has no visible edge in dark mode" was overstated.** White on a dark canvas has plenty of edge contrast. What was actually lost was the *lift* — the shadow and hairline did nothing. Fixed, but it was cosmetic, not Tier 0.
3. **"4 error toasts carry a recovery action" was wrong** — those four were on warning/success paths. **Zero** of the 88 `toast.error` calls had one.

Also: 5 of my own 6 "no responsive breakpoint" leads were false positives. Only `blueprint/slot-editor.tsx:310` is real, and it is flagged as *suspected* rather than confirmed — it is arithmetic, not a device check.

---

## Two decisions only you can make

**1. `GiftOverlay` (396 lines) and `GooeyNav` (224 lines).** Both fully built, both imported nowhere. The visual audit proposes wiring them; the feature audit counts them as carried cost. I deleted the other five dead components and deliberately left these two. Wire them or delete them — carrying them unwired is the only option with no upside.

**2. The three generation engines.** `q_instructions/` (14,173 lines, live), `services/pool/` (9,035, live), `apps/question_generation/` (3,737, **dormant** — flag off by default, no production caller, ships a parity test against the legacy one). That last is a migration that stalled: not dead code but unfinished replacement code, which costs more. Finish it and delete `q_instructions`, or delete it. ~14,000 lines hang on the answer.

---

## Loose ends I could not close

- **`ENABLE_TEST_ENDPOINTS` in production.** `DJANGO_DEBUG` defaults false so the gate is sound, but `deployment/qp-gen-backend.service:9` loads an `EnvironmentFile` that is not in the repo. **Check that `.env` on the host.** (The endpoint it guarded is gone now — it is a management command, `run_engine_slice` — so this is less urgent than it was.)
- **`/api/generation/answer-key`.** Zero callers in this frontend, so it looks deletable. I only proved *this* repo does not call it; check deployment logs before removing.
- **Tooltips (3.7)** — deprioritised, not done. The editor toolbar already carries 29 native `title=` attributes, so those controls are labelled, just with slow unstyled browser tooltips. There is no `components/ui/tooltip.tsx`; the only styled one is inside `ui/ai-prompt-box.tsx` on `@base-ui/react`. Promoting that to a primitive is the real first step.
- **Modal consolidation (3.3)** — partially done. The scrim recipes and z-index scale are unified. Migrating the five hand-rolled modals onto `Dialog` was not attempted: they are five different shapes (centred, full-screen, right drawer) and getting focus traps and portal behaviour wrong is not something I can catch without a browser.

---

## If something looks wrong

Every commit is independent and revertable. The riskiest three, in order:

1. `e03873c` — the route rename. Old paths redirect, but if anything external links to `/paper-library` or `/question-bank`, check the redirects fire.
2. `a633e02` — the display typeface. Revert is repointing `--font-display` and dropping one class from `PageTitle`.
3. `c18a10e` — the document panel restructure. It changed the component from two early returns to one fragment with three children.
