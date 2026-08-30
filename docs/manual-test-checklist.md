# QP-Gen Manual Test Checklist

*Living document. The top section is what is currently shipped-but-unverified; the suites below it are standing regressions to re-run whenever the queue touches that area.*

**Last updated:** 2026-08-31, branch `fix/tier0-quick-fixes` (25 commits, not pushed).

---

## Before anything

- [ ] **`npm install` in `frontend/`.** `recharts` is declared in `package.json:71` (`^3.10.1`) but is **not present in `node_modules`**. Until it installs, `components/admin/usage-analytics.tsx` fails to resolve and the admin usage page will not build. This is pre-existing, not from any recent change.
- [ ] `npm run dev` in `frontend/`, backend running separately.
- [ ] Have a **multi-set paper** (Sets A/B/C) saved — several tests below need one and generating it takes longer than the tests do.

---

## Batch 3 — shipped, not yet verified

The rest of Tier 2, plus two Tier 3 items.

### 3.1 Page titles on one scale + display face — `450a9f3`, `a633e02`
- [ ] Every page heading is the serif (Playfair): papers, questions, templates, settings, admin, admin org detail, landing title.
- [ ] Card titles and dialog titles are **still Inter** — they use a different token on purpose.
- [ ] Settings now has a real `<h1>`; previously it was an `<h2>` with no `<h1>` on the page.
- [ ] Titles are not smeared or fake-bold anywhere (the reason a variable-weight face was chosen).

### 3.2 Loading system — `59dd622`
- [ ] Admin dashboard, admin org detail and teacher invites show a centred page spinner while loading.
- [ ] Templates now loads a **card grid** skeleton, not a stack of bars — watch that the page does not jump when the cards land.
- [ ] Blueprint modal template step shows the same grid skeleton.
- [ ] `/register`, `/onboard`, `/reset-password` on a slow connection show a spinner, not a blank screen.

### 3.3 Status colour tokens — `60ea6a6`
- [ ] Light **and** dark: sync status, design-panel warnings/checks, source-panel warnings, review-tray and comparison badges, the draft marker on papers, the generating pulse.
- [ ] Difficulty chips on the questions list are **unchanged** — deliberately still raw emerald/amber, because difficulty is a scale, not a status.
- [ ] Editor toolbar block-type colours unchanged for the same reason.

### 3.4 Error retry + copy — `cad3c7c`
- [ ] Stop the backend, then load templates / questions / papers / invites / admin. Each error toast shows a **Retry** button, and Retry actually refetches once the backend is back.
- [ ] No error toast says "Failed to …" any more.
- [ ] Validation errors (empty name, nothing selected) have **no** Retry — retrying those would rerun a guaranteed failure.

### 3.5 A4 sheet in dark mode — `d4b75ff`
- [ ] Dark mode editor: the page reads as a lifted sheet, with a soft light edge and a deeper shadow.
- [ ] Light mode unchanged.
- [ ] Exported PDF and print preview have **no** border or shadow baked in.

### 3.6 Dashboard recent papers — `c13f831`
- [ ] Account with papers → empty chat shows up to three, below the prompt box, each opening in the editor. "All papers →" reaches the list.
- [ ] Brand-new account → the row is absent entirely, not an empty heading.

---

## Batch 2 — shipped, not yet verified

Everything in Tier 0 and Tier 1, plus six Tier 2 items. Batch 1 below is still unverified too.

### 2.1 Document panel reachable at every width — `c18a10e`
- [ ] **At 768px and 1023px**, with a multi-set paper: the outline rail is visible on the left, and opening it shows Sets A/B/C. **This was the break — they were unreachable.**
- [ ] Picking a set at that width closes the drawer and switches the set.
- [ ] Tapping the scrim closes the drawer.
- [ ] **At 1280px+**: the panel is a column, not a drawer, and picking a set does **not** close it.
- [ ] Print preview: neither rail nor drawer appears.

### 2.2 Editor opens with one panel — `7ee40a7`
- [ ] At 1366px, a fresh editor: page not clipped, outline collapsed to its rail, dock open.
- [ ] Opening the outline from the rail still works.

### 2.3 Five components deleted — `beb71f4`
- [ ] App builds and every route loads. Nothing else to check — they had no importers.

### 2.4 Empty-state buttons — `6c217ac`
- [ ] Empty papers list → "Open the Editor" navigates. Same on the questions list.
- [ ] Empty templates → "Browse built-in templates" switches the rail **without navigating**.
- [ ] Filter to zero results → still shows Clear filters / Clear search, **not** the new button.

### 2.5 Routes renamed — `e03873c`
- [ ] `/questions` shows the question bank. `/papers` shows saved papers.
- [ ] **Old links redirect:** `/paper-library` → `/questions`, `/question-bank` → `/papers`.
- [ ] Nav labels land on matching URLs — "Question Bank" → `/questions`, "Papers" → `/papers`.
- [ ] Editor toolbar → "Open Paper" reaches the papers list.

### 2.6 Blueprint step dots — `e59d4da`
- [ ] Below 640px: a row of numbered steps under the modal header, and tapping one jumps to it.
- [ ] A step that is not yet reachable stays disabled, exactly as in the rail.
- [ ] Above 640px: no dots, rail as before.

### 2.7 Pinned admin actions — `ae13ac8`
- [ ] Narrow window on the admin members table: Actions stays pinned at the right edge while the rest scrolls under it.
- [ ] Row hover still tints the pinned cell.

### 2.8 One export path — `c0a10b7`
- [ ] Toolbar PDF and DOCX both still download and back up.
- [ ] URL-param `?action=export-pdf` and `?action=export-docx` likewise.
- [ ] Cancelling the filename prompt does nothing — no toast, no error.
- [ ] Filenames: "term test", "term test.pdf" and "term test pdf" should all produce `term test.pdf`.

### 2.9 Grainient merged — `2112200`
- [ ] Landing page shader renders as before.
- [ ] **The regression this guards:** navigate `/` → `/dashboard` **by clicking**, not reloading. The chat backdrop must stay behind the chat and the prompt box must stay on screen.

### 2.10 Editor blank state — `612f74d`
- [ ] New empty paper → card with three actions. Each opens the right thing.
- [ ] **Type on the page without dismissing anything** — the card must not block clicks to the sheet, and disappears once content exists.
- [ ] Opening a saved paper → no flash of the card.
- [ ] During generation → card absent.

### 2.11 Adaptive suggestions — `0574201`
- [ ] Account with papers/templates/bank questions → prompts reference them.
- [ ] Brand-new empty account → the original four generic prompts.
- [ ] Backend down → still the original four, no crash, no empty row.

### 2.12 Engine slice runner — `03b051a`
- [ ] `python manage.py run_engine_slice --help` lists the flags.
- [ ] `curl -X POST .../api/generation/test-science-engine` returns 404 **even with `DJANGO_DEBUG=true`**.
- [ ] Do **not** run the command itself casually — it spends real OpenAI budget.

---

## Batch 1 — shipped, not yet verified

Three commits on `fix/tier0-quick-fixes`. Each test says what a failure means so you know whether to revert or just file it.

### 1.1 Contrast on primary buttons — `958cfbb`

Changed 7 buttons across `editor/page.tsx`, `settings/page.tsx`, `comparison-workspace.tsx`, `review-tray.tsx` from `text-white` to `text-primary-foreground`.

- [ ] **Dark mode**, editor → the two primary action buttons read **ink text on sand**, not white on sand.
- [ ] **Dark mode**, Settings → the theme selector chip, the save button, and the password-change button: same.
- [ ] **Dark mode**, review tray → "Insert selected (n)" reads ink on sand.
- [ ] **Dark mode**, comparison workspace → its primary button reads ink on sand.
- [ ] **Light mode**, all of the above → unchanged, white text on ink. *A regression here means `--primary-foreground` is wrong in the light block, not that the swap was wrong.*
- [ ] **Both modes** → these five are deliberately untouched and must still be white: the emerald button in the editor (`editor/page.tsx:1419`), the emerald tick in the review tray, the two landing-page CTAs, the destructive delete on the brand-kit card.

*Failure = the token resolves differently than expected. Revert is one commit and safe.*

### 1.2 Export cloud backup — `d0070c0`

- [ ] Open a **saved** paper (not a draft) in the editor.
- [ ] Export PDF **from the toolbar** → downloads, and a "Saved to cloud." toast follows. *This path already worked; it is the control.*
- [ ] Export PDF via **URL param** — navigate to the editor with `?action=export-pdf` → downloads **and** now shows "Saved to cloud." **Before this fix it downloaded and silently never uploaded.**
- [ ] Same via `?action=export-docx`.
- [ ] On a **multi-set** paper, export Set B via URL param → the upload lands against the base paper, not `{base}_B`. Check the backend export records if you can; the visible symptom of the old bug was simply no "Saved to cloud." toast.
- [ ] On an **unsaved draft** → no upload attempted, no error toast. `persistablePaperId` should return null and skip it.

*Failure = check `lib/s3-upload.ts` accepted `setLabel`; it is declared at `:31` and appended at `:52`, so a 400 would point at the backend's `set_label` handling instead.*

### 1.3 Failed-sync shake — `07e3103`

- [ ] Editor open with a paper. Kill the network (devtools offline, or turn off wifi).
- [ ] Edit something to trigger a save → the **"Sync failed"** badge shudders side to side, twice, then settles.
- [ ] The **"Offline"** badge above it still pulses as before.
- [ ] Enable OS/browser **reduced motion** → repeat. The badge appears with **no** movement at all.

*Failure = the class name or the keyframe name mismatched. Cosmetic only; nothing else depends on it.*

---

## Standing regression suites

Run the relevant suite whenever the queue touches that area.

### Editor layout
*Re-run after any editor layout change.*

- [ ] At **1920px** — outline, page, and dock all visible, page not clipped.
- [ ] At **1366px** — the common laptop. Page not clipped horizontally in the default state.
- [ ] At **1024px** — the `lg` boundary. Panels first appear here.
- [ ] At **768px** — the outline rail is present and opens as a drawer; the dock shows its rail.
- [ ] **Multi-set paper at every width above** — Sets A/B/C reachable and switchable. *This was the break below 1024px; fixed in `c18a10e`, so it is now a regression guard.*
- [ ] Collapse and reopen each panel from its rail.

### Export
- [ ] PDF and DOCX, from both the toolbar and the URL param.
- [ ] Print (`?action=print`) → only the active set's pages appear in the dialog.
- [ ] Exported PDF has **no** page shadow or hairline border baked in (`export-pdf.ts` neutralises them on the clone).

### Generation
- [ ] Generate from the **dashboard chat**.
- [ ] Generate from the **blueprint modal**.
- [ ] Build from the **question bank**.
- [ ] Start from a **template**.
- [ ] Navigate away mid-generation and back → run still visible and progressing.
- [ ] Full page **reload** mid-generation → run reattaches.
- [ ] Multi-set run → Sets B and C arrive and are adoptable.

### Theming
*Re-run after any token or colour work — queue items 2.9, 2.10.*

- [ ] Toggle light/dark on every route: landing, login, register, dashboard, editor, templates, papers, question bank, settings, admin.
- [ ] Nothing unreadable, nothing invisible, no white-on-white or ink-on-ink.
- [ ] The A4 sheet still reads as a lifted page in both themes.

### Empty states
*Re-run after queue item 1.3.*

- [ ] Fresh account, no data → paper library, question bank, templates each show their empty state.
- [ ] Filter/search to zero results → the *filtered* empty state appears with a working Clear button. **These already work; do not break them.**

---

## Where the rest of the work is

`docs/work-queue.md` holds **30 tracked items** across four tiers, drawn from the three audits. Not a million, but enough to pick from for a long time:

- **Tier 0** — 1 item left (0.1, the outline vanishing below 1024px, ~1 hr). The other three shipped as Batch 1 above.
- **Tier 1** — 6 quick wins.
- **Tier 2** — 11 substantial but well-defined.
- **Tier 3** — 9 larger or needing a decision first, including the three-engine question.

Two decisions are still open and block nothing else until you make them: wire-or-delete `GiftOverlay`/`GooeyNav`, and the engine question.
