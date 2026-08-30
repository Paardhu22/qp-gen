# QP-Gen UX Guidance Audit

*Audited at `main@5996aa4`, 2026-08-30. Scope: guidance only — how the product tells a teacher what it is, what to do next, and how to recover. Visual design, motion, and design-system consistency are audited separately in [`ui-audit-and-animation-playbook.md`](./ui-audit-and-animation-playbook.md); nothing in this file duplicates that one.*

---

## Table of Contents

1. [The finding in one line](#the-finding-in-one-line)
2. [What guidance already works](#what-guidance-already-works)
3. [The handoff map](#the-handoff-map)
4. [Layout friendliness](#layout-friendliness)
5. [Guidance gaps](#guidance-gaps)
6. [Proposals](#proposals)
7. [Implementation prompts](#implementation-prompts)
8. [Execution order](#execution-order)

*Scope note on layout: this file covers layout only where it decides whether a teacher can **reach or understand** a task — a control that disappears at a given width, a default arrangement that does not fit the screen it targets, an off-screen action with no signal. Spacing rhythm, density, and visual consistency are the other document's.*

---

## The finding in one line

**Guidance is excellent inside purpose-built panels and absent at every seam between them.**

Where someone sat down and designed a surface as a *task* — the blueprint modal, the review tray, org onboarding — the guidance is genuinely good: step rails, live summaries, self-describing headers, forced visits to steps a teacher would otherwise skip. Where the product hands off from one surface to another, or greets someone with nothing, guidance stops entirely. The app describes the next action in prose and does not offer a control that performs it.

This is not a design-skill problem. The patterns already exist in the codebase. They have not been propagated.

---

## What guidance already works

These are the reference patterns. New guidance work should copy these, not invent alternatives.

### Blueprint modal — the strongest surface in the app
`components/blueprint/blueprint-modal.tsx`

Three steps on a navigable rail (`:138-140`), with a live summary that never leaves the screen. The header comment (`:13-34`) states the design intent explicitly: steps are *navigable, not sequential*, because a wizard that forces a sequence is one "they will avoid, and the only genuine dependency is that step 1 produces the blueprint steps 2 and 3 edit."

Then it does the harder thing — it protects the teacher from a skip that silently breaks the run, at `:310-313`:

> `// one step the paper cannot be generated without — a teacher who never sees step 2 has no chapter attached, and finds out only when...`

That is guidance reasoning about a *failure that happens later*. It is the highest bar met anywhere in this codebase.

### Review tray — self-describing, with the mental model stated
`components/review-tray.tsx:166-170`

> Pick which generated questions go into your paper. Inserted items stay here as a record — use Undo to pull one back out.

One sentence establishes purpose, and a second pre-empts the "why is this still here?" confusion. Actions carry live counts — `Insert selected (3)`, `Insert all (12)` (`:174-190`) — so the button states what it will do, not what it is.

### Organization onboarding — a real step flow
`components/onboard-organization-form.tsx`

Three steps plus an interstitial (`:22-26`), a rendered step rail with `aria-current="step"` (`:317-339`), and a Skip affordance on the logo step so an admin is never trapped. The comment at `:215` shows the same later-failure reasoning as the blueprint modal — it refuses to strand an admin on the last step over an optional field.

### Dashboard starter prompts — right idea, frozen
`app/(dashboard)/dashboard/page.tsx:66-71, 781-788`

Four suggestion chips under a "What can I help with?" heading. This is the app's only feature-discovery surface. See [Gap 5](#gap-5--the-only-discovery-surface-is-hardcoded) for why it underdelivers.

---

## The handoff map

Every point where a teacher finishes something and must find the next thing.

| Handoff | What the product does | Verdict |
|---|---|---|
| Land on `/dashboard` first time ever | Identical screen to session #500 | **Broken** — no first-run state exists |
| Chat → paper generation | Blueprint modal takes over, guides properly | **Good** |
| Generation → questions | Review tray explains itself | **Good** |
| Review tray → editor | No transition guidance | **Weak** |
| Editor → saved | `toast.success("Saved to cloud.")`, then nothing | **Broken** — never says where it went |
| Saved → find it again | Nav labels point at the wrong URLs | **Broken** — see [Gap 6](#gap-6--nav-labels-and-urls-are-swapped) |
| Any empty list → first item | Prose naming the next step, no control | **Broken** ×3 |
| Any error | Statement of failure, no way forward | **Broken** ×95 |

The two Good rows are both inside the generation flow. Everything outside it is unguided.

---

## Layout friendliness

The short version: **the codebase holds three different answers to "this panel doesn't fit," and the editor picked the worst one.**

Same problem, three solutions, all shipped:

| Component | Answer when the panel won't fit | Verdict |
|---|---|---|
| `components/editor/generate-dock.tsx:150-215` | Collapses to a 48px rail with a vertical "Generate paper" label; below `lg` the rail routes straight to the full-screen Builder | **Best** — and the reasoning is written down at `:150-153` |
| `app/(dashboard)/templates/page.tsx:307, 378` | Rail hides at `lg`, replaced by a horizontal scrolling strip that mirrors it | **Good** |
| `components/editor/document-outline.tsx:178, 193` | Disappears entirely | **Broken** — see Gap 9 |

There is no convention. Each surface decided independently, and one of them decided to drop the feature.

### The editor's default arrangement does not fit the screen it targets

Both panels default to open — `app/(dashboard)/editor/page.tsx:232-233`:

```tsx
const [outlineOpen, setOutlineOpen] = useState(true);
const [dockOpen, setDockOpen] = useState(true);
```

Add up what that asks for:

| Piece | `lg` (1024px+) | `xl` (1280px+) |
|---|---|---|
| Document outline | 240px (`w-60`) | 256px (`xl:w-64`) |
| A4 page | 794px | 794px |
| Generate dock | 320px (`w-[320px]`) | 360px (`xl:w-[360px]`) |
| **Total** | **1,354px** | **1,410px** |

The panels first appear at `lg` — 1024px — leaving **464px of room for a 794px page**. Even at `xl` the requirement exceeds the breakpoint. A 1366×768 laptop, the ordinary machine in an Indian staff room, has roughly 1,350px usable after the scrollbar: still short at every tier.

So on the most likely hardware, a teacher's first view of the app's main workspace is cramped, and their first action is closing a panel someone chose to open for them. The individual panels are well built. The default composition of them was never checked against a real screen.

### Dashboard sidebar — the pattern done right
`app/(dashboard)/dashboard/page.tsx:672-679, 730-734, 745`

Overlay with `absolute` positioning below `lg`, `lg:static` above it, a scrim correctly gated with `lg:hidden`, and a labelled toggle (`aria-label="Show sessions"`). Closes on scrim click and on session select (`:268, :283`). Nothing to fix — cited as the reference for Gap 9.

---

## Guidance gaps

### Gap 1 — Empty states name the exit and don't open it
**Severity: high · Effort: low · The best ratio on this list**

Three zero-states describe the next action in prose and ship no control that performs it. A teacher reading one is, by definition, already stuck and already looking for the way out.

`app/(dashboard)/paper-library/page.tsx:758-761`

```tsx
<p className="max-w-xs text-xs text-muted-foreground">
  Generate and save questions from the Editor to see them here.
</p>
```

`app/(dashboard)/question-bank/page.tsx:969-972`

```tsx
<p className="max-w-xs text-xs text-muted-foreground">
  Create a paper in the Editor and save it to see it here.
</p>
```

`app/(dashboard)/templates/page.tsx:531-535` — points at a "Built-in" tab, which is at least on-screen, but still as prose rather than as a control.

All three name the Editor or a tab. None link to it. The copy is already written and already correct; it needs a button underneath, not a rewrite.

Note the *filtered*-empty variants do this right — `paper-library:751-757` and `question-bank:975-982` both render a working **Clear filters** / **Clear search** button. The pattern is present in the same file, three lines away from where it is missing.

### Gap 2 — There is no first-run state, and no way to build one
**Severity: high · Effort: medium · Gates most other work**

A search across `app/`, `components/`, `lib/`, and `store/` for `localStorage` keys matching `seen|onboard|tour|intro|first|welcome|dismiss` returns **zero results**. Nothing in the product can distinguish a teacher's first session from their five-hundredth.

This is a missing primitive, not a missing screen. Until it exists, no guidance anywhere can be conditional, which means every hint must either be permanent clutter for experienced users or absent for new ones. That constraint is why several gaps below cannot be fixed properly in isolation.

**Do not confuse this with `components/ui/onboarding-welcome-screen.tsx`.** Despite the filename, it is imported only by `components/login-form.tsx:13` and is login-page art. It is not product onboarding and is not wired to any first-run logic.

### Gap 3 — The editor is a guidance desert
**Severity: high · Effort: medium**

`app/(dashboard)/editor/page.tsx` is 1,432 lines and contains no hint, tip, help affordance, or blank-state guidance. A teacher arrives at a blank A4 page beside a 1,468-line toolbar (`components/editor/toolbar.tsx`) with nothing indicating a first move.

The editor is also the destination the *other* broken empty states point at — Gap 1's copy sends teachers here specifically. Fixing Gap 1 without fixing this routes them from one dead end to a larger one.

The blueprint modal sits one click away and demonstrates exactly the treatment this surface needs.

### Gap 4 — Errors state failure and offer nothing
**Severity: medium · Effort: medium**

95 `toast.error` calls across `app/` and `components/`. **Zero carry an `action:`.** Every failure in the product is a dead end.

Four toasts in the codebase do carry actions, and all four are on non-error paths — destructive confirms and undo:

- `app/(dashboard)/paper-library/page.tsx:509` — Delete
- `app/(dashboard)/question-bank/page.tsx:325` — Undo
- `app/(dashboard)/question-bank/page.tsx:376` — Delete
- `components/editor/toolbar.tsx:1430` — Clear the entire paper

So the product knows how to offer a recovery control. It offers them only when it is about to destroy something, never when it has just failed at something.

The copy is also two voices: **12** errors open `"Failed to …"`, **9** open `"Could not …"`, with the remainder in other shapes. Several are recoverable and say so without offering the retry — `"Failed to load question bank. Please refresh."` asks the teacher to perform an action the toast could perform itself.

### Gap 5 — The only discovery surface is hardcoded
**Severity: medium · Effort: low-medium · Depends on Gap 2**

`app/(dashboard)/dashboard/page.tsx:66-71`:

```tsx
const SUGGESTIONS = [
  "Make a class 10 Science unit test on Light.",
  "What does the class 10 English paper look like?",
  "Draft a note to parents about the term test.",
  "Explain the CBSE competency-based question format.",
];
```

Four static strings, identical for every teacher forever. They never reflect what the teacher has, and they never reveal that Templates, the Question Bank, or saved blueprints exist. A teacher who only ever uses the chat may never learn the rest of the product is there.

`isEmpty` is already computed at `:649` but is used only to set `autoFocus` on the prompt box (`:657`). The hook for a state-aware empty screen is present and unused.

### Gap 6 — Nav labels and URLs are swapped
**Severity: medium · Effort: low · Correctness bug, not polish**

`components/top-navbar.tsx:33-35`:

```tsx
{ icon: ListChecks, label: "Question Bank", href: "/paper-library" },
{ icon: FileText,   label: "Editor",        href: "/editor" },
{ icon: BookOpen,   label: "Papers",        href: "/question-bank" },
```

"Question Bank" navigates to `/paper-library`. "Papers" navigates to `/question-bank`. Every bookmark, every shared link, and every URL a teacher reads describes the opposite of where it goes.

Commit `cceebf4` fixed the on-page heading and deliberately deferred the route rename as a separate task. It is still deferred. This is wayfinding, so it is tracked here rather than in the visual audit.

### Gap 7 — Tooltips are effectively unused
**Severity: low · Effort: medium**

`Tooltip` appears in 3 files out of 79 components: `app/(dashboard)/dashboard/page.tsx`, `components/admin/usage-analytics.tsx`, `components/ui/ai-prompt-box.tsx`.

The dense icon-only surfaces — the editor toolbar above all — carry none. Worth doing only after Gap 3, since a toolbar that explains itself icon-by-icon is a weaker fix than one that explains the task.

### Gap 8 — Success is terminal
**Severity: low · Effort: low**

`toast.success("Saved to cloud.", { duration: 2000 })` ends the flow. A teacher who has just finished a 30-minute task is told it worked and not where it went or what is available next. Combined with Gap 6, finding that paper again requires trusting a nav label that is wrong.

### Gap 9 — The outline vanishes below 1024px and takes the set switcher with it
**Severity: high · Effort: low · This one loses a feature, not just guidance**

`components/editor/document-outline.tsx` hides at `lg` in *both* of its states — the open panel at `:193` (`hidden w-60 … lg:flex`) and the collapsed rail at `:178` (`hidden w-12 … lg:flex`). Below 1024px there is no panel, no rail, no button, no trace that the outline exists.

That would be tolerable if the outline only listed pages. It doesn't. The Set A/B/C tabs render **only** inside it, at `:216`:

```tsx
{tabs.map((tab) => {
```

Confirmed by search: `setTabs` / `activeSetTab` / `onSelectTab` appear nowhere outside `app/(dashboard)/editor/page.tsx:1126-1128` (where they are passed *in*) and `document-outline.tsx` (where they are rendered). There is no second switcher.

**Consequence:** a teacher on a tablet or a sub-1024px laptop who generates a multi-set paper can see Set A and cannot reach Set B or C. The sets generate, save, and export fine — they are simply unreachable in the UI at that width. The feature is intact and the layout hides it.

This is the sharpest finding in this document, and the cheapest to fix, because the answer is already written twice in the same repo. `generate-dock.tsx:150-161` even explains its reasoning:

> `// A phone has no room for a 320px panel beside a 794px page, so below lg the rail is the whole feature`

The dock asked the question. The outline never did.

### Gap 10 — The blueprint modal inverts its own stated intent on small screens
**Severity: low · Effort: low**

The step rail is `hidden w-48 … sm:block` (`components/blueprint/blueprint-modal.tsx:518`), so it disappears below 640px. Back/Next in the footer (`:802-823`) render at every width, so navigation survives — nobody is trapped.

But the file's header comment (`:29-34`) argues specifically that steps must be **navigable, not sequential**, because a wizard that forces a sequence is one teachers "will avoid." Below `sm`, with only Back and Next, it becomes exactly the wizard it was designed not to be. The intent inverts silently and the code still reads as though it holds.

Low severity — phone-width paper authoring is presumably rare. Logged because the reasoning is explicit in the file and the behaviour quietly contradicts it. A row of numbered step dots under the header would restore direct access in very little space.

### Gap 11 — Off-screen table actions have no signal
**Severity: low · Effort: low**

`components/admin/members-table.tsx:89-95` renders seven columns: Name, Email, Role, Status, Tokens used, Est. spend, **Actions**.

Nothing clips — the shared primitive wraps every table in `overflow-x-auto` (`components/ui/table.tsx:11`), which also **refutes** the earlier concern that this file carries no responsive handling. It inherits it.

The guidance problem is what's left: on a narrow screen the last columns sit off-screen with no indication they exist, and the hidden one on the far right is Actions — approve, reject, remove. An admin on a phone sees a members list that appears to have no controls. Horizontal scroll is a discoverable affordance only when something signals it: a fade at the edge, a sticky Actions column, or a stacked card layout below `md`.

---

## Proposals

### A. Give every empty state a control

Add a primary action button beneath the existing copy in all three zero-states, reusing the button treatment already present in each file's filtered-empty branch. Copy stays as written.

- `app/(dashboard)/paper-library/page.tsx` → **Open the Editor**
- `app/(dashboard)/question-bank/page.tsx` → **Open the Editor**
- `app/(dashboard)/templates/page.tsx` → **Browse built-in templates** (switches the tab in place)

### B. Build the first-run primitive

A `useFirstRun(key)` hook over `localStorage` returning `{ seen, markSeen }`, with namespaced keys (`qpgen:seen:editor`, `qpgen:seen:dashboard`, …). Small, but everything conditional depends on it. Must degrade safely when storage is unavailable — treat unknown as *seen*, so a returning teacher is never re-onboarded by a privacy setting.

### C. Editor blank state

When the editor holds no document, replace the empty A4 with a panel offering the three real entry points: **Generate a paper** (opens the blueprint modal), **Build from the question bank** (`components/editor/build-from-bank-dialog.tsx` already exists), **Start from a template**. Give it the blueprint modal's treatment — short purpose line, named actions, no tour.

### D. Error recovery pass

Across the 95 `toast.error` calls: add `action:` wherever a retry or a navigation would help, and settle on one voice. Recommend `"Could not …"` — it reads as the system's fault rather than the teacher's, and it is already the voice used by the more recently written call sites.

### E. State-aware dashboard suggestions

Derive `SUGGESTIONS` from what the teacher actually has rather than from a constant. No papers yet → starter prompts. Has templates → "Reuse your Class 10 blueprint". Has a question bank → "Build a paper from my saved questions". Doubles as feature discovery for the surfaces the chat currently hides.

### F. Rename the routes to match the labels

`/paper-library` → `/question-bank`, `/question-bank` → `/papers`. Add redirects from the old paths so existing bookmarks survive. Update `top-navbar.tsx` and every internal `href`.

### G. Give the outline the treatment the dock already has

Copy `generate-dock.tsx`'s answer rather than inventing one: keep the collapsed rail visible at **all** widths so the outline is always reachable, and below `lg` surface the set tabs as a horizontal strip — the pattern `app/(dashboard)/templates/page.tsx:378` already ships. Whichever is chosen, the rule to establish is that **a panel may collapse, but a feature that lives only inside it may not disappear.**

### H. Pick a default editor arrangement that fits 1366px

Open one panel by default, not two. The dock is the stronger candidate to keep — it is how papers get made — leaving 1366 − 320 = 1,046px for a 794px page, which fits with room for margins. The outline opens on demand from its rail. Alternatively keep both and collapse the outline automatically under a width threshold; the fixed default is what needs to go, not the panels.

### I. Signal off-screen table columns

Below `md`, either stack member rows as cards or pin the Actions column. If horizontal scroll stays, add an edge fade so it reads as scrollable. Applies to `members-table.tsx` first, then any other table that grows past four columns.

---

## Implementation prompts

### 1. Empty-state controls

> In `app/(dashboard)/paper-library/page.tsx`, `app/(dashboard)/question-bank/page.tsx`, and `app/(dashboard)/templates/page.tsx`, add a primary action button to the *unfiltered* empty branch of each. Keep the existing explanatory copy exactly as written and place the button below it. Match the button styling already used in the filtered-empty branch of the same file (`paper-library:751-757`, `question-bank:975-982`). The paper-library and question-bank buttons navigate to `/editor`; the templates button switches to the built-in tab in place rather than navigating. Do not touch the filtered-empty branches — they already work.

### 2. First-run primitive

> Create `lib/use-first-run.ts` exporting `useFirstRun(key: string)` returning `{ seen: boolean, markSeen: () => void }`, backed by `localStorage` under namespaced `qpgen:seen:*` keys. It must be SSR-safe (no storage access during render on the server) and must treat any storage failure as `seen: true`, so a teacher with storage blocked is never repeatedly onboarded. Add no UI in this change — the hook lands on its own so the surfaces that need it can adopt it independently.

### 3. Editor blank state

> In `app/(dashboard)/editor/page.tsx`, when no document is loaded, render a guidance panel in place of the blank page. Three actions: "Generate a paper" (opens the blueprint modal), "Build from the question bank" (opens `components/editor/build-from-bank-dialog.tsx`), "Start from a template". One short purpose line above them. Follow the tone of `components/review-tray.tsx:166-170` — state what the surface is for and what happens next, in one sentence, no more. Gate any *dismissible* portion on `useFirstRun("editor")`; the three actions themselves are permanent, not first-run-only.

### 4. Error recovery pass

> Audit all 95 `toast.error` call sites under `app/` and `components/`. For each, decide: is it recoverable by retry, by navigation, or not at all? Add `action: { label, onClick }` to the first two categories — mirror the shape already used at `app/(dashboard)/question-bank/page.tsx:325`. Normalise all opening phrasing to `"Could not …"`. Delete instructions that tell the teacher to perform an action the toast can perform itself (e.g. `"Failed to load question bank. Please refresh."` becomes `"Could not load the question bank."` with a Retry action). Do not change what triggers the toasts — copy and actions only.

### 5. State-aware suggestions

> Replace the constant `SUGGESTIONS` at `app/(dashboard)/dashboard/page.tsx:66-71` with a function of the teacher's current state — paper count, template count, question-bank size. Return four suggestions, always including at least one that references a product surface the teacher has not used yet, so the chat also does discovery work. Keep the existing chip rendering at `:781-788` unchanged.

### 6. Route rename

> Rename `/paper-library` → `/question-bank` and the existing `/question-bank` → `/papers`, so URLs match the nav labels in `components/top-navbar.tsx:33-35`. Add permanent redirects from both old paths in `next.config.ts`. Update every internal `href`, `router.push`, and `redirect` referencing either path. Verify no backend route or saved-link generator depends on the old paths before renaming.

### 7. Keep the outline reachable at every width

> In `components/editor/document-outline.tsx`, the collapsed rail at `:178` and the open panel at `:193` are both `hidden … lg:flex`, so the component vanishes below 1024px. The Set A/B/C tabs render only inside it (`:216`) and exist nowhere else in the app, so multi-set papers lose Sets B and C at that width.
>
> Make the collapsed rail visible at all widths, and below `lg` render the set tabs as a horizontal scrolling strip — copy the pattern already shipping at `app/(dashboard)/templates/page.tsx:378`. Read `components/editor/generate-dock.tsx:150-215` first; it solves this exact problem for the opposite side of the page and its approach should be mirrored, not re-invented.
>
> Verify at 768px and 1023px that the set tabs are reachable and switching sets still works.

### 8. Make the editor's default arrangement fit a 1366px laptop

> `app/(dashboard)/editor/page.tsx:232-233` opens both editor panels by default. Outline (240px, `xl` 256px) + A4 page (794px) + dock (320px, `xl` 360px) needs 1,354px at `lg` and 1,410px at `xl`; the panels first appear at 1024px and a 1366px laptop has ~1,350px usable.
>
> Change the default so only the generate dock opens; `outlineOpen` starts `false` and the teacher opens it from its rail. Do not remove either panel or change their widths — the defaults are the bug. Complete task 7 first, so the outline still has a rail to open from.
>
> Verify at 1024px, 1366px, and 1920px that the page is never clipped in the default state.

### 9. Signal off-screen table columns

> `components/admin/members-table.tsx:89-95` renders 7 columns, the last being Actions. `components/ui/table.tsx:11` already wraps every table in `overflow-x-auto`, so nothing clips — do not add another scroll container. The problem is that on a narrow screen the Actions column is off-screen with nothing indicating it exists.
>
> Below `md`, either pin the Actions column or stack each member as a card. If horizontal scroll is kept, add an edge fade that appears only while more content exists to the right. Apply to `members-table.tsx` only; leave other tables until this pattern is settled.

---

## Execution order

| Phase | What | Gap | Effort | Depends on | Why here |
|-------|------|-----|--------|-----------|----------|
| 1 | Outline reachable at every width | 9 | ~1 hr | — | Only item that restores a **lost feature**. Answer already exists twice in the repo |
| 2 | Empty-state controls | 1 | ~1.5 hr | — | Best ratio. Copy exists, pattern exists three lines away, three dead ends become doors |
| 3 | Editor default arrangement fits 1366px | — | ~30 min | 1 | Two-line change. Needs the outline rail from phase 1 to open from |
| 4 | Route rename | 6 | ~1 hr | — | Correctness bug. Independent — can run any time |
| 5 | First-run primitive | 2 | ~3 hr | — | Missing primitive. Nothing conditional is possible until it lands |
| 6 | Editor blank state | 3 | ~3 hr | 5 | Worst guidance gap, and the destination phase 2 routes teachers to |
| 7 | Error recovery pass | 4 | ~2.5 hr | — | 95 dead ends. Mechanical, parallelisable, no design decisions |
| 8 | State-aware suggestions | 5 | ~2 hr | 5 | Feature discovery. Needs first-run state to know what "new" means |
| 9 | Off-screen table signal | 11 | ~1 hr | — | Admin-only, but Actions is what's hidden |
| 10 | Success handoffs | 8 | ~1 hr | 4 | Pointless before the routes are honest |
| 11 | Blueprint step dots below `sm` | 10 | ~45 min | — | Restores stated intent. Low reach |
| 12 | Tooltips on dense surfaces | 7 | ~2.5 hr | 6 | Weakest fix — only worth doing once the editor explains the task |

Phases 1 → 3 are the layout spine and land in ~1.5 hours combined.
Phases 5 → 6 → 8 are the guidance spine.
Phases 2, 4, 7, 9 are independent of everything; any is a clean first commit.

**Total: ~19.25 hours.**

The reordering from the first draft is deliberate: layout work moved ahead of guidance work because a hint is worthless on a control the teacher cannot reach, and phase 1 is the only item here that restores functionality rather than improving explanation.

---

## Open questions

- **Does a teacher-role user ever see org onboarding?** `components/onboard-organization-form.tsx` is the guided path, but `components/register-form.tsx` (the teacher path) has no step rail — it is a single form plus a verification-code step (`:310`, `:340-441`). If teachers are the majority of users, the good onboarding is on the minority path. Not yet verified.
- **Where does a teacher invited by an admin land first?** `components/admin/teacher-invites.tsx` exists; the accept-invite landing experience has not been traced.
- **Is the review tray still on by default?** Prior planning noted an intent to flip `insertionMode` from `"review"` to `"auto"`, which would make the tray a pass over already-placed questions rather than a gate. If that shipped, the tray's self-describing copy at `:166-170` now describes the wrong model.
