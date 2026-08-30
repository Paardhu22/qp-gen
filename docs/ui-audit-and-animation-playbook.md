# QP-Gen UI Audit & Animation Playbook

*Extended to full coverage at commit `5996aa4` (2026-08-30). The original pass covered 4 of 15 routes and 8 of 79 components (~19% of frontend LOC); this revision audits all 14 user-facing routes (the 15th, `/pagination-harness`, is an internal layout-measurement harness with no design surface) and 61 of 79 components — every route, plus the whole editor, templates, blueprint, admin, settings and auth clusters. The 18 components not individually audited are unmodified shadcn primitives under `components/ui/`.*

> Branch: `ui-revamp/theme-consistency` | Date: 2026-07-28 | Updated: 2026-07-28  
> Stack: Next.js 16.2.6, App Router, Tailwind CSS, Framer Motion, OGL WebGL, shadcn/ui  
> Palette: ink `#282d3c` (oklch 0.2990 0.0282 270.30) / sand `#D7C3A3` (oklch 0.8257 0.0486 79.53)

---

## Table of Contents

1. [UI Audit — What's Working](#ui-audit--whats-working)
2. [UI Audit — Issues](#ui-audit--issues)
3. [UI Proposals](#ui-proposals)
4. [Animation Audit — Inventory](#animation-audit--inventory)
5. [Animation Audit — Dead Zones](#animation-audit--dead-zones)
6. [Animation Audit — Unused Assets](#animation-audit--unused-assets)
7. [Implementation Prompts](#implementation-prompts)
8. [Execution Order](#execution-order)

---

## UI Audit — What's Working

### Color system
The ink/sand palette is well-executed. Light mode uses white canvas with ink `#282d3c` as primary and sand-derived warm tones for muted/accent surfaces. Dark mode inverts correctly — ink becomes the background (deepened to `oklch(0.21 0.023 271)`), sand becomes primary. The `--brand-ink` / `--brand-sand` anchors in `globals.css:186-187` let any surface reference the literal palette rather than semantic roles. oklch throughout the token layer — no sRGB rounding issues. (Outside `globals.css` this does not hold: 127 raw hex literals remain in `.tsx`, and `styles/editor.css` carries 105 more. Most are legitimately literal — printed-paper black, the toolbar's ink swatches, the gift/curtain SVGs — but the admin chart tokens and the editor's page elevation are not. See Issues 10 and 16.)

### Dashboard chat experience
The dashboard (`app/(dashboard)/dashboard/page.tsx`) is the strongest page. The AI assistant chat is a genuine working surface, not a stats board. The ChatBackdrop uses an ink/sand Grainient (sand `#D7C3A3` → white → sand) that correctly matches the palette. The PromptInputBox, FollowUpCards, and PressCheck generation visualization are cohesive.

### Press-check generation animation
Four CSS keyframes (`pc-pulse` :77, `pc-fan` :95, `pc-rake` :135, `pc-strike` :226) in `styles/press-check.css` create a print-shop metaphor during paper generation. Has its own scoped color system (`--pc-ground`, `--pc-sheet`, `--pc-ink`, `--pc-reg`) that derives from the ink/sand palette. Visually distinctive.

### Auth eye-tracking
The login form (`components/login-form.tsx`) has cursor-tracking eyes that follow the mouse (range ±20px horizontal, ±10px vertical), blink every 3s (200ms duration), and close when the password field is focused. A memorable signature moment.

### Curtain theme toggle
Full-screen `scaleY` portal animation (550ms, `cubic-bezier(0.76, 0, 0.24, 1)`) in `components/ui/curtain-theme-toggle.tsx`. Three variants: default, appbar, icon. Hover scale 1.1, press scale 0.96. Dramatically reveals the theme swap.

### Mobile responsiveness
Solid foundation: safe-area utilities (`pt-safe`, `pb-safe`, etc.), 44px touch targets on `pointer: coarse`, iOS text-size-adjust fix, horizontal overflow prevention, no-scrollbar utility, font-size ≥16px on inputs to prevent iOS zoom.

### Loading primitives
`components/ui/spinner.tsx` and `components/ui/skeleton.tsx` (shipped in `661f191`) are the best-documented components in the app. Both encode their invariants in the docstring rather than at the call site — one fill (`bg-muted/40`), one animation, two spinner sizes, and an explicit rule that a skeleton's height must match the row it stands in for. `<Spinner size="page">` even reasons about colour inheritance so it does not wash out on a `bg-primary` button. The problem is adoption, not design (Issue 18).

### Admin chart colour tokens
`components/admin/usage-analytics.tsx:150-160` is the only place in the app that defines a scoped colour layer properly: `--viz-1` / `--viz-2` / `--viz-grid` / `--viz-axis`, with separate dark-mode steps chosen for the dark card surface rather than derived from the light ones, and the CVD ΔE figures recorded in the file header (`:14`). Every chart mark then reads `var(--viz-*)`. This is the pattern the status colours in Issue 10 should copy. Two caveats: the values are raw sRGB hex (`#2a78d6` / `#eb6834`) in a codebase the audit describes as oklch throughout, and the blue/orange pair has no relationship to ink/sand — it is a second palette, defensible for categorical data but currently undeclared as such.

### Editor paper simulation
The TipTap/ProseMirror editor renders A4 pages (794×1123px) with print-ready structure. Paper breakdown (`lib/paper-breakdown.ts`) walks the doc tree to extract section/question/mark stats. The PaperPreview component provides a read-only viewer.

---

## UI Audit — Issues

### ~~1. Nav labels are swapped~~ — DONE ✓
> Fixed in `cceebf4`. Heading on `/question-bank` corrected to "Papers". Nav labels kept as-is (route names are misleading but renaming routes is a separate task).

### ~~2. Landing page Grainient uses off-palette purple~~ — DONE ✓
> Fixed in `cceebf4`. Landing Grainient switched from lavender `#b39de3` to sand `#D7C3A3` / `#efe4d2`. Default Grainient props in both component copies updated from pink/indigo to ink/sand.

### ~~3. Landing page hardcodes dark theme elements~~ — DONE ✓
> Fixed in `cceebf4` + `0216c05`. `bg-neutral-950` replaced with `bg-[#efe4d2]` (sand). Landing CTAs moved to ink `#282d3c`. 89 hardcoded zinc-\* greys across 7 files mapped to semantic tokens.

### ~~4. Editor toolbar has orphaned purple color~~ — DONE ✓
> Fixed in `cceebf4`. `text-purple-500` removed from toolbar OR Group item.

### 5. No dashboard home page
**Status:** Open  
**Problem:** The dashboard route (`/dashboard`) drops directly into the AI chat. There's no overview/home state showing recent papers, quick stats, or entry points to other features. The chat IS the dashboard.

**Impact:** A teacher returning to the app sees a blank chat prompt instead of a summary of their work. New users don't know the app has a paper library, question bank, or builder until they explore the nav.

### 6. Settings page is minimal
**Status:** Open (low priority)  
**Problem:** Settings only has password change and theme toggle (via curtain toggle). No profile editing, no preferences for paper defaults (board, class, subject), no notification settings.

**Impact:** Low — functional for now, but feels incomplete for a SaaS.

### 7. Empty states are static and bare
**Status:** Partial — breathing animation on icons done (`cceebf4`), but no illustration, no CTA button, no guided onboarding.  
**Problem:** The question-bank and paper-library pages show a dashed-border box with an icon and text when empty. The icon now breathes (`empty-breathe` keyframe, 4s), but there's still no action guidance for new users.

### 8. No display/serif typeface for content hierarchy
**Status:** Open  
**Problem:** The entire app uses Inter for everything — headings, body, labels, the landing page title. Inter is a workhorse UI face but gives no typographic personality to the brand. The press-check component uses its own `--pc-serif` (Georgia) and `--pc-mono` stack internally, but these don't surface anywhere else.

**Impact:** The typography is technically correct but anonymous. A display face on the landing title and major headings would distinguish the product.

---

*Issues 9–21 come from the `5996aa4` coverage extension: the editor, templates, blueprint, admin, settings and auth clusters, which the original pass never opened. Every claim below is cited `file:line` and was read in the source, not inferred.*

### 9. `text-white` on `bg-primary` is unreadable in dark mode

**Status:** Open — **highest-severity finding in this pass**
**Problem:** Seven call sites hardcode `text-white` on a `bg-primary` surface instead of using `text-primary-foreground`:

| File:line | Control |
|-----------|---------|
| `app/(dashboard)/editor/page.tsx:1253` | "Save paper" primary CTA |
| `app/(dashboard)/editor/page.tsx:1320` | "Generate questions" primary CTA |
| `app/(dashboard)/settings/page.tsx:170` | Password-flow step indicator (active) |
| `app/(dashboard)/settings/page.tsx:217` | "Verify & Continue" primary CTA |
| `app/(dashboard)/settings/page.tsx:332` | "Save password" primary CTA |
| `components/comparison-workspace.tsx:338` | Set-approval CTA |
| `components/review-tray.tsx:178` | "Insert all" CTA |

The palette inverts in dark mode by design — `globals.css:261` sets `--primary: oklch(0.8257 0.0486 79.53)` (sand `#D7C3A3`) and `globals.css:262` sets `--primary-foreground` to ink. Hardcoding white defeats that.

**Impact:** White `#ffffff` on sand `#D7C3A3` measures **1.72:1** contrast (relative luminance 0.561 vs 1.0). The correct token pairing — ink on sand — measures **7.98:1**. Every primary action in the editor, in Settings, in the review tray and in the comparison workspace is effectively invisible in dark mode. `components/settings/brand-kit-card.tsx:177` has the same defect against `bg-destructive`.

### 10. ~~There is no `--success` or `--warning` token~~ — PREMISE WRONG, work now DONE ✓

> **Correction, 2026-08-31.** The tokens exist and always did in this revision:
> `globals.css:196-200` (light) and `:269-273` (dark) define `--success`,
> `--success-foreground`, `--warning` and `--warning-foreground`, and
> `@theme inline:141-144` maps all four. Three call sites were already using
> them. The finding was right about the symptom and wrong about the cause —
> the gap was **adoption**, not absence.
>
> Fixed in `60ea6a6`: the genuine status uses now go through the tokens.
> Three groups stay hardcoded deliberately, because they are not status —
> `questions/page.tsx` `difficultyTint` (a scale; its own comment argues a
> hard question is not an error), and the toolbar's block-type colour coding
> plus the two buttons that mirror it.

**Original problem statement, kept for the shade counts:** `globals.css` defines `--destructive` (`:196` light, `:269` dark). Counted with `grep -rn '(green|emerald)-[0-9]00' app/ components/ --include=*.tsx`:

- **Success / "live" green:** 10 distinct shades — `emerald-100/300/400/500/600/700/900`, `green-400/500/600` — across 10 files: `editor/page.tsx`, `paper-library/page.tsx`, `comparison-workspace.tsx`, `editor/generate-dock.tsx`, `editor/toolbar.tsx`, `file-upload.tsx`, `hsat-source-picker.tsx`, `paper-design-panel.tsx`, `review-tray.tsx`, `tiptap-editor.tsx`.
- **Warning amber/orange:** 10 distinct shades — `amber-100/300/400/500/600/700/800/900`, `orange-400/600` — across 8 files.
- **Error:** the `--destructive` token *is* used, 52 times outside `components/ui/`, but 12 raw `red-*` occurrences in 5 files still bypass it — including `editor/toolbar.tsx:1171` (`text-red-400 hover:text-red-300`, which gets *lighter* on hover against a light toolbar) and `:1436` (`text-red-400` "Clear All" at 10px).

The clearest symptom is two indicators for one state: `editor/toolbar.tsx:1461` renders a `bg-green-500 animate-pulse` "Live Sync" dot while `editor/generate-dock.tsx:189-190` renders a `bg-emerald-400`/`bg-emerald-500` `animate-ping` badge — same meaning, different hue, different keyframe.

**Impact:** 71 hardcoded palette-colour utilities remain across 14 files. Issue 3 mapped 89 `zinc-*` greys to tokens in `0216c05`; this is the same problem in the surfaces that pass never reached, and it cannot be fixed by mapping alone, because there is no semantic token to map *to*.

**Verified NOT violations** (checked, deliberately literal, leave alone): `editor/toolbar.tsx:118-143` — a 26-swatch text-colour picker; those are the teacher's ink choices, printed on paper. `templates/template-preview-paper.tsx:69-141` — 19 `neutral-*` utilities rendering an A4 paper mock-up, correct for the same reason `styles/editor.css` is black-on-white.

### 11. The Insert-block menu invented a seven-colour rainbow the palette does not have

**Status:** Open
**Problem:** `components/editor/toolbar.tsx:424-610` assigns each block type an identity colour: Header `text-teal-500` (`:427`), Instructions `text-amber-500` (`:450`), Section `text-primary` (`:467`), Question `text-emerald-500` (`:483`), MCQ `text-rose-500` (`:494`), Assertion–Reason `text-fuchsia-500` (`:516`), Grouped `text-sky-500` (`:606`). Six of the seven are literal Tailwind hues; the seventh is the semantic token. Issue 4 removed a `text-purple-500` from this exact list in `cceebf4` — leaving six siblings that are the same category of mistake.

The same pattern repeats one row up in the toolbar's quick actions, where three adjacent buttons of identical function carry three colour schemes, each with hand-written dark-mode pairs: "Add Existing" `text-emerald-600 … dark:text-emerald-400 dark:hover:bg-emerald-950/30` (`:1313`), "New Paper" `text-primary … dark:hover:bg-primary/30` (`:1329`), "Open Paper" `text-amber-600 … dark:hover:bg-amber-950/30` (`:1343`).

**Impact:** The app's most colourful surface is the one place a teacher inserts structure, and none of those colours exist anywhere else in the product. Fixing this needs a decision first — either an accent ramp derived from ink/sand, or ink-only with icons carrying the distinction.

### 12. Five hand-rolled modals bypass the `Dialog` primitive, each with its own scrim and layer

**Status:** Open
**Problem:** `components/ui/dialog.tsx` exists, is theme-aware, and animates (`:34` overlay `fade-in-0`, `:58` popup `zoom-in-95`, both `duration-100`, both with matching `data-closed` exits). Five surfaces reimplement it from scratch instead:

| File:line | Scrim | Layer | Enter/exit animation |
|-----------|-------|-------|----------------------|
| `components/ui/dialog.tsx:34` — the primitive | `bg-black/10` + `backdrop-blur-xs` | `z-50` | yes |
| `components/ui/alert-dialog.tsx:101` | `bg-black/50` + `backdrop-blur-sm` | `z-50` | — |
| `app/(dashboard)/settings/page.tsx:135-138` | `bg-black/50` + `backdrop-blur-sm` | `z-50` | none |
| `components/templates/template-editor-panel.tsx:185-187` | `bg-black/50` + `backdrop-blur-sm` | `z-50` | none |
| `components/editor/header-logo-picker.tsx:106-110` | `bg-black/50` + `backdrop-blur-sm` | `z-[60]` | none |
| `components/editor/build-from-bank-dialog.tsx:218-220` | `bg-black/50` + `backdrop-blur-sm` | `z-[9999]` | none |
| `components/top-navbar.tsx:195` — drawer scrim | `bg-black/40` + `backdrop-blur-sm` | `z-50` | Framer |
| `app/(dashboard)/dashboard/page.tsx:732` — sidebar scrim | `bg-black/30`, no blur | `z-20` | none |

Five scrim recipes at four opacities. None is theme-aware: `bg-black/50` over an ink `#282d3c` background in dark mode is a scrim you cannot see, which is exactly when a scrim matters most.

**Impact:** "A modal appeared" animates in one place in the app and hard-cuts in five. The modal a teacher opens most — Build from bank — is the one that jumps to `z-[9999]`.

**Verified working:** `components/blueprint/blueprint-modal.tsx:492-494` *does* use the real `DialogContent`, overriding it to `h-[min(88vh,900px)] w-[min(96vw,1100px)]`. It is the model the other five should follow.

### 13. Nine z-index values, four ad-hoc escapes above the `z-50` layer, no scale

**Status:** Open
**Problem:** `globals.css` documents no z-index scale. Counted across `app/` and `components/`: `z-50` ×18, `z-10` ×14, `z-40` ×2, `z-30` ×1, `z-20` ×1, plus four escapes above the shadcn `z-50` layer, one of which a `z-` grep cannot even find:

- `components/GiftOverlay.tsx:366` — `z-[60]`
- `components/editor/header-logo-picker.tsx:106` — `z-[60]`
- `components/editor/question-hover-menu.tsx:148` — **inline `style={{ zIndex: 60 }}`**, not a utility
- `components/editor/build-from-bank-dialog.tsx:218` — `z-[9999]`

`components/top-navbar.tsx:84` (sticky header) and `app/(dashboard)/editor/page.tsx:1034` (mobile review tray) both claim `z-40` in the same stacking context; they do not currently collide only because the tray is pinned to `bottom-0`.

**Impact:** Every new overlay is a guess. The `z-[9999]` is the signature of that guess having been made under pressure.

### 14. Nine font sizes below 14px, none on the type scale

**Status:** Open
**Problem:** 149 arbitrary-value font sizes across `app/` and `components/` (`grep -rno 'text-\[[0-9.]*\(px\|rem\)\]'`), in **14 distinct values**: 9, 9.5, 10, 10.5, 11, 11.5, 12, 12.5, 13, 14, 15 px plus `0.65rem`, `0.7rem`, `0.8rem`. Nine of those steps sit below Tailwind's `text-sm`. Distribution: `text-[11px]` ×46, `text-[10px]` ×44, `text-[13px]` ×14, `text-[12px]` ×13, `text-[11.5px]` ×10, `text-[10.5px]` ×6, `text-[9px]` ×4.

Densest offenders: `editor/toolbar.tsx` (23), `editor/generate-dock.tsx` (23), `paper-design-panel.tsx` (13), `question-bank/page.tsx` (12), `blueprint/blueprint-modal.tsx` (10). `components/paper-design-panel.tsx` alone uses 13, 12.5, 12, 11.5, 11 and 10.5px inside 247 lines (`:108,119,141,151,164,169,171`) — six sizes spanning 2.5px.

**Impact:** There is no readable hierarchy at that resolution; 11px and 11.5px are not a distinction anyone perceives, they are two different numbers. And `admin/usage-analytics.tsx:249,256,315,332,398,411` sets chart tick text via `fontSize: 11` inline, so even the charts are off-scale in a third syntax.

### 15. Every route styles its own page title

**Status:** Open
**Problem:** Eight surfaces, eight treatments — five sizes, three weights, and two of them are not headings at all:

| Route | Element | Class | file:line |
|-------|---------|-------|-----------|
| Settings | `<h2>` | `text-3xl font-bold tracking-tight` | `settings/page.tsx:369` |
| Dashboard | `<h1>` | `text-2xl font-semibold tracking-tight sm:text-3xl` | `dashboard/page.tsx:769` |
| Admin (platform) | `<h1>` | `text-2xl font-semibold` | `admin/page.tsx:215` |
| Admin (org detail) | `<h1>` | `text-2xl font-semibold` | `admin/organizations/[id]/page.tsx:75` |
| Papers | `<h1>` | `text-lg font-semibold tracking-tight` | `question-bank/page.tsx:703` |
| Q-Bank | `<h1>` | `text-lg font-semibold tracking-tight` | `paper-library/page.tsx:595` |
| Templates | `<h1>` | `text-sm font-semibold` | `templates/page.tsx:337` |
| Editor | `<span>` | `text-[14px] font-medium` | `editor/page.tsx:1110-1117` |

Settings is the only page whose title is an `<h2>` — that document has no `<h1>`. The editor's title is a `<span>` with no heading semantics at all. Templates' page title (`text-sm`, 14px) is *smaller* than its own card headings (`template-card.tsx:98`, `text-sm font-semibold`) and the same size as its body text.

**Impact:** Moving between routes, the reader's eye has to re-find "where is the title" every time. This is also the precondition for Issue 8 — a display typeface cannot be applied consistently to a hierarchy that does not exist.

### 16. `styles/editor.css` is theme-blind

**Status:** Open
**Problem:** 1361 lines, **105 hardcoded colour literals against 4 `var(--…)` uses**, and **zero `.dark` selectors and zero `prefers-color-scheme` queries** (`grep -n '\.dark\|prefers-color-scheme' styles/editor.css` → no matches). Most of it is correct: the sheet is black-on-white because a printed CBSE paper is black on white (`:24`, `:45`, `:122`). The problem is the chrome that lives in the same file and is not paper:

- **`.doc-page` elevation (`:55-61`)** — `border: 1px solid rgb(0 0 0 / 0.08)` plus a three-layer `rgb(15 23 42 / …)` shadow stack, both documented as the thing that makes the sheet read as lifted. `globals.css:640` deliberately darkens the canvas in dark mode (`color-mix(in oklab, var(--background) 90%, black)`) — and a slate shadow under a white sheet on a near-black canvas renders nothing. The canvas got dark-mode treatment; the sheet's elevation did not, so in dark mode the page has no edge at all.
- `.paper-header-action.is-active` (`:328-329`) — `background: #18181b`, zinc-950, editor chrome, off-palette.
- `.block-drag-handle` (`:460`, `:475`, `:481`) — `#999` → `#333` → `#000` with `rgba(0,0,0,0.07)` / `0.12` backgrounds.
- `.section-title` (`:367`) — `background-color: #4b5563`, a slate grey printed onto the paper where brand ink `#282d3c` is the obvious choice.

The node-view components feed this file rather than Tailwind: `editor/extensions/drawing-node.tsx:112-157` and `float-image.tsx:145-215` reference `.drawing-toolbar`, `.drawing-tool`, `.float-img-btn`, `.float-img-divider`. That is a second, parallel, untokenised styling system inside the app's largest surface.

**Related:** `components/paper-preview.tsx:183` gives the preview canvas `bg-muted/40`, while `globals.css:636-641` gives the editor canvas `color-mix(in oklab, var(--muted) 60%, var(--background))` with a separate `.dark` inversion. Two recipes for the same visual object — "the surface a sheet of paper rests on". And `templates/template-preview-paper.tsx:70` renders its mock-up in Tailwind `font-serif` (a Georgia-first stack) while the real paper is `"Times New Roman", Times, serif` (`styles/editor.css:25`), so the preview does not typeset like the thing it previews.

### 17. `animate-shake` does not exist

**Status:** Open (5-minute fix; listed separately because it is a silent failure)
**Problem:** `components/tiptap-editor.tsx:382` renders the "Sync failed" state with `animate-shake`. There is no `shake` keyframe in `app/globals.css` (0 matches), in `styles/` (0 matches), or in `node_modules/tw-animate-css/dist/tw-animate.css` (0 matches). The class resolves to nothing.

**Impact:** The one state in the editor that needs to interrupt the teacher — autosave failed — is the one styled to move and doesn't. The three sibling states at `:363`, `:369` and `:376` all animate correctly.

### 18. Loading treatment is standardised in `components/ui/` and ignored in half the app

**Status:** Partial — the primitives shipped in `661f191`, the migration did not finish
**Problem:** `components/ui/spinner.tsx` says in its own docstring: *"The app's only spinner. Two sizes on purpose"* (`default` = size-4 inline, `page` = size-8 centred). The codebase disagrees in both directions:

- **14 raw `Loader2` + `animate-spin` call sites** bypass `<Spinner>` entirely, at five sizes none of which is `page`: `h-6 w-6` ×5 (`admin/page.tsx:240,344,392`, `admin/organizations/[id]/page.tsx:47,70`), `h-5 w-5` ×1 (`admin/teacher-invites.tsx:141`), `h-4 w-4` ×3 (`editor/header-logo-picker.tsx:136`, `onboard-organization-form.tsx:665`, `settings/brand-kit-card.tsx:129`), `h-3.5 w-3.5` ×5 (`editor/build-from-bank-dialog.tsx:380`, `editor/header-logo-picker.tsx:210`, `school-switcher.tsx:90`, `settings/brand-kit-card.tsx:210`, `templates/template-editor-panel.tsx:379`). The unconverted half is, almost exactly, the surfaces the original audit never opened: admin, settings, templates, onboard, editor overlays.
- Of the 17 sites that *do* use `<Spinner>`, 8 override the size anyway with `className="size-3"` / `"size-3.5"`.

Skeleton shape has the same split. `components/ui/skeleton.tsx` warns that `height` *"must match the real row it stands in for — a skeleton that is the wrong height moves the page when the data lands"*. `app/(dashboard)/templates/page.tsx:416` loads a two/three-column card grid behind `<SkeletonRows rows={6} height="h-24" />`, which renders one vertical stack of 96px bars — wrong axis, wrong count, guaranteed reflow. The correct pattern already exists in a sibling component: `components/blueprint/template-picker-grid.tsx:176-179` renders `grid gap-3 sm:grid-cols-2 lg:grid-cols-3` of `<Skeleton className="h-24 rounded-xl border border-border" />`.

Three auth routes render a **completely blank full-viewport div** as their Suspense fallback — no spinner, no skeleton, no content: `app/(auth)/register/page.tsx:9`, `app/(auth)/onboard/page.tsx:8`, `app/(auth)/reset-password/page.tsx:10`, all `<div className="flex min-h-svh items-center justify-center" />` with no children.

### 19. `prefers-reduced-motion` coverage has four holes

**Status:** Partial
**Problem:** The guarded surfaces are genuinely good — `globals.css:573` and `:620` scope micro-interactions and empty-state breathing to `no-preference`, `globals.css:508` disables the landing title and fades, `styles/press-check.css:252` handles the generation animation, `components/ui/grainient.tsx:272-273` paints one static frame, `GiftOverlay.tsx:67` uses Framer's `useReducedMotion`. Not covered:

1. `@keyframes loading-bar` (`globals.css:462`) has no guard anywhere. Its only consumer is `editor/generate-dock.tsx:298` — an indeterminate bar that sweeps for **minutes** during a generation run.
2. `components/GooeyNav.css` contains 3 keyframes (`pill` :137, `particle` :168, `point` :196) and **zero** reduced-motion rules. This matters because Phase 7 plans to wire it into the navbar.
3. `admin/usage-analytics.tsx` never sets `isAnimationActive`, so recharts' 1500ms draw-in runs unconditionally on `:273`, `:321`, `:404`.
4. The register-page eye rig (`register-form.tsx:281-300`) uses inline `transition: all 0.15s ease` / `0.1s ease` with no guard of any kind.

### 20. The signature auth animation is in the wrong file, duplicated, and half of it was lost

**Status:** Open
**Problem:** The original audit credited cursor-tracking eyes to `components/login-form.tsx`. That file is 160 lines and contains no eye code — `grep -rn 'eyePos|isTyping|blink'` returns hits in exactly two files:

- `components/register-form.tsx:57-60, 275-303` — the live copy, on the **register** page.
- `components/ui/cloud-watch-form.tsx:10-13, 54-68` — a near-identical second copy, **imported nowhere** (see Unused Assets).

Login instead renders `WelcomeScreen` (`login-form.tsx:13, 57`) — a Framer Motion staggered entrance with 7 `motion` elements (`ui/onboarding-welcome-screen.tsx:37-139`) — which the original inventory never recorded at all.

Two further corrections: the pupil transform is `translate(${eyePos.x}px, 0px)` (`register-form.tsx:298`), so there is **no vertical tracking**; and both copies set literal `backgroundColor: "black"` / `"white"` (`:286`) rather than tokens.

The rig also depends on a remote asset: `register-form.tsx:271` loads `https://pub-940ccf…r2.dev/cloud.jpg` through a plain `<img>` with no `width`/`height` inside a `relative h-44 w-full max-w-[300px]` box. `next.config.ts` declares no `images.remotePatterns`, so this cannot become a `next/image` without config work — it is unoptimised, unsized, and the eyes are positioned over it with hardcoded offsets (`top: 60, left: "26.7%"`).

### 21. Auth is light-only by construction, and the auth shell is copy-pasted six times

**Status:** Open
**Problem:** `components/auth-theme-scope.tsx:7-26` strips `dark` from `<html>` and sets `data-auth-page`, which `globals.css:221-227` keys off. That is a deliberate, documented decision — but it runs in a `useLayoutEffect`, i.e. after hydration, so a dark-mode user landing on `/login` gets a dark frame before the class is removed.

Downstream of that decision the glass card is written out longhand six times, identically:

`w-full max-w-md rounded-2xl border border-white/30 bg-white/30 p-6 sm:p-8 shadow-xl backdrop-blur-md`

— at `login-form.tsx:87`, `register-form.tsx:254`, `forgot-password-form.tsx:46`, `reset-password-form.tsx:112`, `onboard-organization-form.tsx:268` and `:309`. There is no shared `AuthCard`. Two consequences are visible on screen:

- `onboard-organization-form.tsx:309` uses `max-w-lg` where its own sibling state at `:268` uses `max-w-md`, so the card **changes width between steps of one flow**.
- `login-form.tsx:55` uses a third shell for the welcome state — `max-w-sm h-[600px] rounded-3xl … bg-white` (opaque, `rounded-3xl`, fixed 600px height) — so login's own two states differ in width, radius, opacity and height, with no transition between them.

### 22. Responsive lead — 5 of 6 flagged files confirmed clean, 1 is real

**Status:** Investigated; mostly refuted
**Problem:** Six files contain no `sm:` / `md:` / `lg:` prefix at all. Checked each against its rendering context rather than trusting the grep:

| File | Verdict |
|------|---------|
| `components/school-switcher.tsx` | **Fine.** Renders only inside fixed-width containers — a `DropdownMenuContent` (`top-navbar.tsx:154`) and the mobile drawer (`:264`) — and returns `null` entirely when the user belongs to fewer than 2 schools (`:47`). Nothing to make responsive. |
| `components/templates/template-card.tsx` | **Fine.** A grid cell; the parent owns the columns (`templates/page.tsx:418,432`). Uses `flex-wrap` internally (`:169`, `:180`) and `truncate`/`min-w-0` on the title (`:91`). |
| `components/templates/template-preview-paper.tsx` | **Fine.** An `aspect-[210/297]` A4 mock inside `max-w-lg` (`:68-69`) — scales fluidly by construction. |
| `components/templates/folder-rail.tsx` | **Fine.** Its only mount point is `templates/page.tsx:307`, an `<aside className="hidden w-60 … lg:flex">`. It never renders below `lg`; the phone equivalent is the chip row at `templates/page.tsx:378-410`. The `opacity-0 … focus-visible:opacity-100` hover-reveal (`:223`) is acceptable for the same reason — desktop-only, pointer-fine. |
| `components/admin/members-table.tsx` | **Degrades, doesn't break.** Seven columns including a three-button action cell (`:117-146`) with no stacking, but `components/ui/table.tsx:9-13` wraps every table in `relative w-full overflow-x-auto`, so it pans. The cost is that the action column — the only interactive part — is the one off-screen at phone width. |
| `components/blueprint/slot-editor.tsx` | **Suspected real, not visually confirmed.** `:310` sets `grid-cols-[2rem_1fr_4.5rem_auto_2rem]` with `gap-2`. Fixed tracks plus gaps consume ~168px before the `auto` column; it renders inside `blueprint-modal.tsx:649` (`p-6`) within `w-[min(96vw,1100px)]`, leaving roughly 130px for the `1fr`. Because a grid `1fr` track has `min-width: auto`, a long slot label will push the row wider than the pane rather than truncating. Needs a device check to confirm the overflow; the arithmetic says it is tight. |

**Also found while checking:** `app/(dashboard)/templates/page.tsx:340-343` hides the "New Template" button entirely below `sm` (`className="ml-2 gap-2 hidden sm:flex"`) with no replacement in the mobile chip row. And the same card grid is laid out on two different breakpoint ladders — `sm:grid-cols-2 xl:grid-cols-3` at `templates/page.tsx:418,432` versus `sm:grid-cols-2 lg:grid-cols-3` at `blueprint/template-picker-grid.tsx:152,176` — so between 1024px and 1279px the same content is 2-up in one place and 3-up in the other.

### 23. Eleven `rounded` utilities sit off the radius scale

**Status:** Open (low priority)
**Problem:** `globals.css:161-167` defines a derived radius scale from `--radius: 0.625rem` (`:210`). Usage is mostly disciplined — `rounded-lg` ×102, `rounded-sm` ×52, `rounded-full` ×52, `rounded-xl` ×26, `rounded-2xl` ×18. But 11 uses of bare `rounded` resolve to Tailwind's fixed 0.25rem default, which is not on that scale, and they cluster in the surfaces the original pass never covered: `admin/page.tsx:269,274`, `templates/folder-rail.tsx:223,337`, `templates/template-card.tsx:102,127`, `templates/template-preview-paper.tsx:88`, `review-tray.tsx:18,295,298`, `editor/build-from-bank-dialog.tsx:296`.

---

## UI Proposals

### ~~A. Purge stray indigo/purple~~ — DONE ✓
> Shipped in `cceebf4`.

### ~~B. Fix nav label / heading mismatch~~ — DONE ✓
> Shipped in `cceebf4`. Heading fixed, nav labels kept (route rename deferred).

### ~~C. Landing page theme awareness~~ — DONE ✓
> Shipped in `cceebf4` + `0216c05`. Sand base color, semantic tokens.

### D. Dashboard home state
**Status:** Open  
Add a home view to the dashboard that shows before the user starts chatting:
- Recent papers (last 3-5, clickable to editor)
- Quick stats (papers generated, questions in bank)
- Shortcuts to Builder, Question Bank
- The chat prompt at the bottom, ready to use

**File:** `app/(dashboard)/dashboard/page.tsx`

### E. Rich empty states with CTAs
**Status:** Partial (icon breathing done, CTA + illustration not done)  
Upgrade the empty states from bare dashed boxes to guided onboarding moments:
- A larger, more expressive icon or simple illustration
- A headline + subtitle explaining what belongs here
- A primary CTA button ("Generate your first paper" → `/dashboard`)
- Secondary action ("or import from PDF" if applicable)

**Files:** `app/(dashboard)/question-bank/page.tsx`, `app/(dashboard)/paper-library/page.tsx`

### F. Display typeface for headings
**Status:** Open  
Add a display face for the landing page title and major section headings. Load via `next/font/google` alongside Inter. Candidates:
- **Playfair Display** — editorial weight, pairs with Inter's neutrality
- **DM Serif Display** — warmer, matches the sand palette
- **Space Grotesk** — geometric but not sterile, if serif feels wrong

**Files:** `app/layout.tsx`, `app/globals.css`, `app/page.tsx`

---

## Animation Audit — Inventory

### Summary stats

*Recounted at `5996aa4`. Method for each figure is stated so it can be re-derived.*

| Metric | Count |
|--------|-------|
| CSS @keyframes | **12** — `grep -rn "@keyframes" app/ components/ styles/`. 5 in `globals.css` (loading-bar :462, landing-shimmer :474, landing-rise :486, landing-fade :497, empty-breathe :608), 4 in `styles/press-check.css` (pc-pulse :77, pc-fan :95, pc-rake :135, pc-strike :226), 3 in `components/GooeyNav.css` (pill :137, particle :168, point :196). `styles/editor.css` (1361 lines) defines **zero**. The doc's earlier "8" omitted the three GooeyNav frames and miscounted press-check as five |
| Framer Motion surfaces | **5 files / 25 `<motion.*>` elements** — `grep -rln "framer-motion"`: `GiftOverlay.tsx` (12 elements, 3 `AnimatePresence`), `ui/onboarding-welcome-screen.tsx` (7), `top-navbar.tsx` (3), `ui/ai-prompt-box.tsx` (2), `dashboard/follow-up-card.tsx` (1). No file imports from `motion/react`. The doc's "10+ surfaces" was right in spirit but two of the five surfaces it named — the prompt box and the follow-up cards — are one element each, and the largest Framer surface in the app (the login welcome screen) was not listed at all |
| Tailwind animation utilities | `animate-spin` ×18, `animate-in` ×10, `animate-pulse` ×7, `animate-out` ×6, `animate-ping` ×1, `animate-bounce` ×1, `animate-none` ×1, `animate-[loading-bar…]` ×1, `animate-shake` ×1 (**dead — no such keyframe exists anywhere**, see Issue 17) |
| Recharts chart animation | 2 chart types (`AreaChart`, `BarChart` ×2) in `components/admin/usage-analytics.tsx`, all running recharts' **default** 1500 ms draw-in — no `isAnimationActive` is set anywhere in the file |
| WebGL shaders | 1 (Grainient — OGL, GLSL ES 300, Perlin noise + sinusoidal warp + film grain) |
| CSS micro-interactions | Button press scale(0.97), card hover lift, empty-state breathe |
| Page transitions | 0 |

### Animation density by page

*Re-audited at `5996aa4`. The `Builder` row is removed — `app/(dashboard)/build-paper/` has been deleted (the Templates page replaced it; see the file header at `app/(dashboard)/templates/page.tsx:5-8`). The `Editor` and `Login/Register` rows were wrong and are corrected below.*

| Page | Density | What's there |
|------|---------|-------------|
| Landing | Rich | Grainient shader (sand tones, continuous) + shimmer (7s) + staggered fade entrance (0.9s) |
| Login | Moderate | Framer Motion staggered welcome screen (`ui/onboarding-welcome-screen.tsx`, 7 `motion` elements). **No eye tracking** — `login-form.tsx` contains no eye code at all (see Issue 20) |
| Register | Rich | Eye cursor tracking (`register-form.tsx:275-303`) — horizontal only, blink, typing detection. Inline styles, no `prefers-reduced-motion` guard |
| Dashboard | Moderate | ChatBackdrop Grainient (sand, continuous) + press-check (4 keyframes) + follow-up card stagger + prompt box + paper design panel |
| Editor | **Moderate–Rich** | Refuted, not dead. `animate-[loading-bar_1.6s]` indeterminate sweep + `<Progress>` (`generate-dock.tsx:294-299`), `animate-ping` live badge (`:189`), per-question `animate-in fade-in slide-in-from-bottom-1` keyed on count (`:309`), hover-menu `fade-in-0 zoom-in-95 duration-100` (`question-hover-menu.tsx:155`), find-replace `slide-in-from-top-2` (`find-replace.tsx:223`), 8 opacity transitions on block handles (`styles/editor.css`), 18 `transition-*` in the toolbar. The page renders **no spinner at all** — the load state is a `<Skeleton>` (`editor/page.tsx:1112`) |
| Papers (question-bank) | Dead | Empty-state breathe only — no row animation, no transitions |
| Q-Bank (paper-library) | Dead | Empty-state breathe only |
| Templates | Dead | 4 `transition-colors` / `transition-opacity` on hover states (`folder-rail.tsx:123,200,223`, `template-card.tsx:95`) and one save spinner (`template-editor-panel.tsx:379`). No card entrance, no filter re-flow, no panel enter/exit — `TemplateEditorPanel` is mounted by a bare ternary (`templates/page.tsx:457,502`) with no `AnimatePresence` |
| Admin | Dead (accidental motion only) | The only movement on the whole surface is recharts' **default** 1500 ms area/bar draw-in in `admin/usage-analytics.tsx:273,321,404` — nobody chose it, it has no reduced-motion guard, and it is the slowest animation in the app. Otherwise 6 raw `Loader2 animate-spin` and a single `transition-colors` (`usage-analytics.tsx:214`) |
| Settings | Dead | Curtain theme toggle only. The password-change modal (`settings/page.tsx:135-143`) is hand-rolled and enters with **no** animation, unlike the shadcn `Dialog` it sits beside |

### Full inventory

| Surface | Technology | Duration / Timing | File |
|---------|-----------|-------------------|------|
| Landing shimmer | CSS `@keyframes` | 7s linear infinite | `globals.css:474` |
| Landing rise | CSS `@keyframes` | 0.9s ease-out forwards | `globals.css:486` |
| Landing fade | CSS `@keyframes` | 0.9s ease-out forwards | `globals.css:497` |
| Loading bar | CSS `@keyframes` | 1.2s ease-in-out infinite | `globals.css:462` |
| Empty state breathe | CSS `@keyframes` | 4s ease-in-out infinite | `globals.css:608` |
| Button press | CSS `transform` | scale(0.97), 50ms ease | `globals.css:574` |
| Card hover lift | CSS `transform` | translateY(-1px), 150ms ease | `globals.css:597` |
| Landing Grainient | OGL WebGL (GLSL ES 300) | Continuous RAF, pauses off-screen | `components/Grainient.tsx` |
| Dashboard Grainient | OGL WebGL (same shader) | Continuous RAF, sand palette | `components/dashboard/chat-backdrop.tsx` |
| Press-check suite | CSS `@keyframes` (4 total) | pc-pulse, pc-fan, pc-rake, pc-strike + ink fill 0.6s | `styles/press-check.css` |
| Curtain theme toggle | React portal + CSS scaleY | 550ms `cubic-bezier(0.76, 0, 0.24, 1)` | `components/ui/curtain-theme-toggle.tsx` |
| Auth eyes | React state + inline style | Blink, typing detection, `transition: all 0.15s ease` / `0.1s ease`; pupil tracks **X only** (`translate(${eyePos.x}px, 0px)`) | `components/register-form.tsx:275-303` — **not** `login-form.tsx`, which has no eye code (see Issue 20). A near-identical second copy sits in the unused `components/ui/cloud-watch-form.tsx:10-68` |
| Login welcome screen | Framer Motion (7 elements) | Container/item variants, staggered entrance | `components/ui/onboarding-welcome-screen.tsx:37-139` |
| Mobile drawer | Framer Motion slide | 280ms `[0.22, 1, 0.36, 1]` | `components/top-navbar.tsx:175` |
| GiftOverlay | Framer Motion (10+ elements) | Multi-stage ~3s, ribbon + confetti + glow | `components/GiftOverlay.tsx` |
| GooeyNav particles | DOM + SVG `feGaussianBlur` | ~1500ms, 15 particles, springy `linear()` ease | `components/GooeyNav.tsx` + `GooeyNav.css` |
| Follow-up cards | Framer Motion | Staggered fade + slide | `components/dashboard/follow-up-card.tsx` |
| Dialog open/close | Base UI / shadcn | `duration-100`, `fade-in-0 zoom-in-95` in, `fade-out-0 zoom-out-95` out | `components/ui/dialog.tsx:34,58` |
| Generation progress sweep | CSS `@keyframes loading-bar` via arbitrary value | `animate-[loading-bar_1.6s_ease-in-out_infinite]` — **no reduced-motion guard** | `components/editor/generate-dock.tsx:298` |
| Generation live badge | Tailwind `animate-ping` | Default 1s cubic-bezier(0,0,0.2,1) infinite, `bg-emerald-400/500` | `components/editor/generate-dock.tsx:189-190` |
| "Just written" line | tw-animate-css | `fade-in slide-in-from-bottom-1 duration-300`, re-keyed on `generatedCount` | `components/editor/generate-dock.tsx:307-309` |
| Question hover menu | tw-animate-css | `fade-in-0 zoom-in-95 duration-100`, portalled, inline `zIndex: 60` | `components/editor/question-hover-menu.tsx:148,155` |
| Find & Replace bar | tw-animate-css | `slide-in-from-top-2 duration-200`; result count `fade-in duration-200` | `components/editor/find-replace.tsx:223,279` |
| Editor block handles | CSS `transition: opacity` | 8 rules, 0.15s–0.2s ease, hover-reveal only | `styles/editor.css:339,420,458,620,817,918,1118,1171` |
| Toolbar "Live Sync" dot | Tailwind `animate-pulse` | `bg-green-500` — a different green and a different keyframe from the dock's `animate-ping` badge doing the same job | `components/editor/toolbar.tsx:1461` |
| Save-state indicator | Tailwind `animate-pulse` / `animate-spin` / `animate-shake` | Saving: pulse + spin. Offline: pulse. Failed: **`animate-shake`, which does not exist** | `components/tiptap-editor.tsx:363,376,382` |
| Admin charts | Recharts default | ~1500 ms draw-in on 1 area + 2 bar charts, no reduced-motion guard | `components/admin/usage-analytics.tsx:273,321,404` |
| Templates / Blueprint / Admin hover states | CSS `transition-colors` | Tailwind default 150 ms | `templates/folder-rail.tsx:123,200`, `blueprint/blueprint-modal.tsx:510,531`, `admin/usage-analytics.tsx:214` |

---

## Animation Audit — Dead Zones

### Route changes
Instant cut between every page. No exit animation, no enter animation, no shared element. Clicking Dashboard → Papers is a hard jump — the app feels like it's reloading.

### List → detail transitions
Papers list and Question Bank both swap to detail view with zero animation. The row you clicked should morph into the detail card — instead it blinks away.

### Table row entrance
Both data tables (Papers, Q-Bank) render all rows simultaneously with no stagger. 50 rows appearing at once feels like a data dump, not a curated list.

### ~~Empty state icons~~ — DONE ✓
> Icon breathing animation shipped in `cceebf4`. But the empty state still lacks a CTA or illustration — it breathes but doesn't guide.

### Navbar active indicator
Active link gets inverted colors via class swap — no slide, no morph, no pill animation. The GooeyNav component exists with its particle system (`components/GooeyNav.tsx`) but isn't used in the actual top navbar.

### Paper save feedback
Saving a paper shows a plain Sonner toast. No celebration moment, no confetti, nothing to reward completing a 30-minute task. The GiftOverlay component exists for exactly this purpose but isn't wired to any user flow.

### Scroll reveals
Zero IntersectionObserver-driven animations anywhere. Long pages scroll without any content reveal or parallax effect.

---

*Dead zones found in the `5996aa4` coverage extension.*

### Templates card grid
The largest new list surface in the app and it has no motion at all. `templates/page.tsx:418,432` renders the grid; cards do not enter, and they do not re-flow when the folder selection (`:307`) or the search term (`:359-373`) changes the set — the grid is simply a different grid on the next frame. `SavedTemplateCard` (`template-card.tsx:95`) has one `transition-colors hover:border-primary/40` and no lift, so it also opts out of the app-wide `[data-slot="card"]` hover treatment (`globals.css:596-600`) by not being a `Card`.

### Panel enter / exit across the whole app
Five surfaces mount and unmount full panels with a bare ternary and no `AnimatePresence`, so they appear and vanish instantly: `templates/page.tsx:457` and `:502` (`TemplateEditorPanel`), `editor/page.tsx:1077` (`TemplateEditorPanel` again), `editor/page.tsx:1033` (the mobile review tray, a `fixed bottom-0` sheet that should slide), and `settings/page.tsx:135` (the password modal). The app already knows how to do this — `top-navbar.tsx:175` slides the mobile drawer in 280 ms on `[0.22, 1, 0.36, 1]`.

### Admin
No motion was ever authored here. The only thing that moves is recharts' default draw-in (Issue 19). Six loading states are raw spinners; approving or rejecting a member (`admin/members-table.tsx:41-77`) mutates the row in place with no transition, so a status `<Badge>` (`:104`) switches variant between frames.

### The editor's set tabs
`editor/page.tsx:1156` keys `TiptapEditor` on `${editorInstanceKey}-${activeSetTab}-${approvedAt}`, so switching set tabs fully remounts the editor and the paper is replaced with a hard cut. This is the single largest visual change the app can make and it is the one with no transition.

### Question insertion during live generation
The generation run now writes questions onto the page as they arrive — the dock announces each one with a 300 ms `fade-in slide-in-from-bottom-1` (`generate-dock.tsx:307-309`), but the question itself appears in the document with nothing. The feedback is on the status panel; the event is on the paper.

---

## Animation Audit — Unused Assets

### GooeyNav
**File:** `components/GooeyNav.tsx` + `GooeyNav.css`  
A particle-burst navigation with 15-particle explosions, SVG gooey filter (`feGaussianBlur`), and springy `linear()` easing. Fully built. Imported nowhere. The actual top-navbar (`components/top-navbar.tsx`) uses plain CSS hover states with class-swap active indicators.

**Note:** The component references `filter: url("#goo")` in CSS but never renders the `<svg>` with the `<filter id="goo">` definition. This SVG filter needs to be added when integrating.

### GiftOverlay
**File:** `components/GiftOverlay.tsx` (12 `motion` elements, 3 `AnimatePresence`)  
Full-screen gift reveal with ribbon split, confetti, glow orb. Correctly guards on `useReducedMotion()` (`:67`). Not wired to any user flow. It imports `components/ui/GiftBow.tsx` (`:5`).

### CloudWatchForm
**File:** `components/ui/cloud-watch-form.tsx`  
A complete alternative sign-in form carrying a second copy of the cursor-tracking eye rig (`:10-13`, `:54-68`), near-identical to the live one in `register-form.tsx`. Imported nowhere — `grep -rn "cloud-watch-form|CloudWatchForm" app/ components/ lib/` returns only the file itself. This is the app's signature animation existing in two places, one of which nobody can reach. Consolidating the two into one component would fix Issue 20 and delete this file in the same change.

### RibbonCut
**File:** `components/ui/RibbonCut.tsx`  
Imported nowhere, including by `GiftOverlay.tsx`, which imports only `GiftBow`. An unused part of an unused component.

---

## Implementation Prompts

### ~~Prompt: Micro-interactions (CSS-only)~~ — DONE ✓
> Shipped in `cceebf4`. Button press `scale(0.97)` with `[data-no-press]` opt-out, card hover lift `translateY(-1px)`, empty-state breathing. All inside `prefers-reduced-motion: no-preference`.

### ~~Prompt: Grainient color alignment~~ — DONE ✓
> Shipped in `cceebf4`. Landing Grainient: `#fcfcfc` / `#D7C3A3` / `#efe4d2`. Default props in both Grainient copies updated to ink/sand.

### ~~Prompt: Fix nav heading~~ — DONE ✓
> Shipped in `cceebf4`.

### ~~Prompt: Empty state breathing~~ — DONE ✓
> Shipped in `cceebf4`. `@keyframes empty-breathe` 4s ease-in-out infinite, `.empty-breathe` class.

---

### 1. Page transitions via View Transitions API

**Impact:** High  
**Effort:** ~2 hours  
**Files:** `app/layout.tsx`, `components/top-navbar.tsx`, `next.config.ts`, `globals.css`

The single biggest improvement. Next.js 16 supports the View Transitions API. Cross-fade between routes with shared element transitions — the navbar persists, content slides, the active indicator tracks smoothly.

#### Prompt

```
Add page transition animations to the qp-gen Next.js 16 app using the View Transitions API.

Current state:
- Next.js 16.2.6 with App Router, route groups `(auth)` and `(dashboard)`
- Root layout at `frontend/app/layout.tsx` uses Inter font, Providers wrapper, Sonner toaster
- Navbar at `frontend/components/top-navbar.tsx` has 6 nav items with instant class-swap active states
- No page transitions exist anywhere — route changes are hard cuts
- Micro-interactions already exist: button press scale(0.97) with `[data-no-press]` opt-out, card hover lift (globals.css ~line 574)

Requirements:
1. Enable View Transitions in `next.config.ts` (experimental.viewTransition or whatever the Next 16 API requires)
2. Add a cross-fade transition for route-level content (the area below the navbar). Default duration ~250ms
3. The navbar should persist across transitions (no flash). The active nav link's `bg-foreground` pill should animate its position between items using `view-transition-name` on each nav link
4. The mobile drawer in top-navbar.tsx already uses Framer Motion AnimatePresence — leave it untouched
5. Add `@view-transition` CSS rules in `globals.css` to control the animation (fade for `::view-transition-old` / `::view-transition-new`, slide for page content)
6. Respect `prefers-reduced-motion` — disable transitions when reduced motion is preferred
7. Keep the curtain theme toggle at `components/ui/curtain-theme-toggle.tsx` working — it uses a full-screen scaleY portal that should NOT conflict with view transitions

Test by navigating between Dashboard, Papers, Q-Bank, Editor. Each transition should feel like a smooth hand-off, not a page reload.
```

---

### 2. Wire GooeyNav into the main navbar

**Impact:** High  
**Effort:** ~1.5 hours  
**Files:** `components/top-navbar.tsx`, `components/GooeyNav.tsx`, `GooeyNav.css`

The particle-burst nav component is fully built — it just needs integration. Every page switch would trigger a liquid particle burst on the active link.

#### Prompt

```
Integrate the existing GooeyNav particle navigation component into the main top navbar of the qp-gen app.

Current state:
- `frontend/components/GooeyNav.tsx` — fully built particle-burst nav with 15-particle explosions, SVG gooey filter, springy linear() easing. Accepts `items: NavItem[]`, `onNavigate`, `initialActiveIndex`, `animationTime`, `particleCount` props. Currently imported NOWHERE.
- `frontend/components/GooeyNav.css` — companion styles with `@keyframes particle`, `@keyframes point`, `@keyframes pill`, custom `--linear-ease` easing. Colors use `hsl(var(--foreground))` and `var(--background)` — already theme-aware.
- `frontend/components/top-navbar.tsx` — the actual navbar. Has `navItems` array with `{ icon: LucideIcon, label: string, href: string }`. Desktop nav (line ~102) renders plain `<Link>` elements with `cn()` class-swap for active state (`bg-foreground text-background`). Mobile drawer (line ~175) uses Framer Motion slide.
- Micro-interactions already ship: button press scale(0.97) with `[data-no-press]` opt-out on elements that own their own transform (curtain toggle, GooeyNav, press-check).

Requirements:
1. Replace the desktop nav section (the `<nav className="hidden lg:flex ...">` block, lines ~102-121) with the GooeyNav component
2. Map the existing `navItems` array to GooeyNav's `NavItem[]` format. Use the Lucide icons as `item.icon` (render as JSX `<Icon className="h-4 w-4" />`) and labels as text
3. Set `initialActiveIndex` based on `usePathname()` matching against `navItems[].href`
4. Wire `onNavigate` to Next.js `useRouter().push(href)` for client-side navigation
5. The GooeyNav currently lacks an SVG filter element in its JSX — it references `filter: url("#goo")` in CSS but never renders the `<svg>` with the `<filter id="goo">` definition. You need to add this SVG filter (feGaussianBlur stdDeviation ~10, feColorMatrix threshold) either inside GooeyNav.tsx or as a global SVG in the layout
6. Style the GooeyNav container to fit within the navbar height (h-16 lg:h-[4.5rem]) and align with the existing layout (between logo and user dropdown)
7. Keep the mobile drawer completely unchanged — GooeyNav is desktop-only (hidden below lg breakpoint)
8. Update `activeIndex` when pathname changes externally (e.g., browser back/forward, programmatic navigation) using a `useEffect` that syncs pathname to the active index
9. The particle color already uses `var(--foreground)` — verify it works in both light (ink #282d3c) and dark (sand-light) themes

DO NOT modify the mobile drawer or its Framer Motion animations. DO NOT change the logo or user dropdown sections.
```

---

### 3. List → detail morphing transition

**Impact:** High  
**Effort:** ~2 hours  
**Files:** `app/(dashboard)/question-bank/page.tsx`, `app/(dashboard)/paper-library/page.tsx`

When clicking a paper row, the row should expand/morph into the detail split-view. Title stays in place (shared element), metadata slides in, preview fades in.

#### Prompt

```
Add Framer Motion list-to-detail morphing transitions on the Papers (question-bank) and Paper Library pages.

Current state:
- `frontend/app/(dashboard)/question-bank/page.tsx` — split-view layout. Left side has a table of papers (Title, Subject, Class, Board, Created). Clicking a row sets `selectedPaper` state, which shows the detail view on the right (metadata card + paper breakdown via `computePaperBreakdown` + `PaperPreview` component). Currently the detail panel appears instantly with no animation. Also has draft management (IndexedDB), set selector tabs, answer script generation.
- `frontend/app/(dashboard)/paper-library/page.tsx` — similar list/detail pattern for the paper library, with questions grouped by project.
- Framer Motion already installed and used in the project.

Requirements:
1. Wrap each table row's title cell content in a `<motion.span layoutId={`paper-title-${paper.id}`}>` so the title text morphs position when transitioning from list to detail
2. Wrap the detail panel in `<AnimatePresence mode="wait">` with `<motion.div>` that:
   - Enters with `initial={{ opacity: 0, x: 20 }}` → `animate={{ opacity: 1, x: 0 }}`
   - Exits with `exit={{ opacity: 0, x: -10 }}`
   - Transition: `duration: 0.25, ease: [0.22, 1, 0.36, 1]`
3. The metadata card (left side of detail) should enter with a slight upward slide: `initial={{ opacity: 0, y: 12 }}` with 50ms delay
4. The PaperPreview section (right side of detail) should fade in with 100ms delay: `initial={{ opacity: 0 }}` → `animate={{ opacity: 1 }}`
5. When no paper is selected, show the empty state with a `<motion.div>` that fades in
6. Key the AnimatePresence on `selectedPaper?.id` so it re-animates when switching between papers
7. DO NOT modify `paper-preview.tsx` or its rendering logic — only wrap it in motion containers
8. Apply the same pattern to paper-library/page.tsx if it has a similar list/detail layout

Use `layout` prop sparingly — only on the title text, not on the entire row.
```

---

### 4. Staggered table row entrance

**Impact:** Medium  
**Effort:** ~45 minutes  
**Files:** `app/(dashboard)/question-bank/page.tsx`, `app/(dashboard)/paper-library/page.tsx`

Wrap table rows in `motion.tr` with staggered entrance. 30ms per row, capped at 15 rows (450ms total). Makes data feel "dealt" onto the page.

#### Prompt

```
Add staggered row entrance animations to the Papers and Question Bank data tables.

Current state:
- `frontend/app/(dashboard)/question-bank/page.tsx` — renders a `<table>` with `<tbody>` containing paper rows. Each row has: Title, Subject, Class, Board, Created At columns. Rows are mapped from a `papers` array. Has search filter, draft management, set selector.
- `frontend/app/(dashboard)/paper-library/page.tsx` — similar table structure for questions grouped by project. Has search, sort, project filter, question type filter.
- Framer Motion already installed and used in the project.

Requirements:
1. Replace `<tr>` elements in the table body with `<motion.tr>` from framer-motion
2. Each row gets:
   - `initial={{ opacity: 0, y: 8 }}`
   - `animate={{ opacity: 1, y: 0 }}`
   - `transition={{ duration: 0.3, delay: Math.min(index * 0.03, 0.45), ease: [0.22, 1, 0.36, 1] }}`
   - The `Math.min(index * 0.03, 0.45)` caps the stagger at 15 rows — rows 16+ appear together
3. Re-trigger when the data changes (search filter, sort). Use a `key` on the parent that includes filter state
4. Respect `prefers-reduced-motion`: use `useReducedMotion()` from framer-motion and skip animations when reduced motion is preferred
5. Don't animate the `<thead>` — only `<tbody>` rows
6. Apply to both question-bank and paper-library pages

Keep it simple — just opacity + translateY. No scale, no spring physics on table rows.
```

---

### 5. Paper save celebration

**Impact:** Medium  
**Effort:** ~1 hour  
**Files:** `components/GiftOverlay.tsx`, editor save flow

Wire the existing GiftOverlay (or a lighter variant) to fire on successful paper save. 1.5s moment that rewards completing a 30-minute task.

#### Prompt

```
Wire the existing GiftOverlay component (or a lighter confetti variant) to fire on successful paper save in the editor.

Current state:
- `frontend/components/GiftOverlay.tsx` — full-screen gift reveal with ribbon split, confetti, glow orb, 10+ Framer Motion elements. Has reduced-motion support. Currently not wired to any user flow.
- The editor save flow uses `savePaper` action from `frontend/actions/savePaper.ts`. On success, shows a Sonner toast.
- Sonner toaster is configured in `frontend/app/layout.tsx` with `position="top-right" richColors theme="system"`.

Requirements:
1. Read `components/GiftOverlay.tsx` to understand its API — props, trigger, dismiss
2. Create a lightweight variant if full GiftOverlay is too heavy — a small confetti burst (canvas-based, 30-50 particles, 1.5s duration) from the save button position. If GiftOverlay has a `variant`/`size` prop, use a smaller variant
3. Wire to save-success path: after `savePaper` resolves, trigger the animation
4. Auto-dismiss after ~1.5s, no user interaction required
5. Keep the Sonner toast — the celebration is additive
6. Only trigger on manual saves, not auto-save
7. Don't trigger on failures
8. Respect `prefers-reduced-motion`

Keep to 1.5-2 seconds. Don't lock the UI.
```

---

### 6. Scroll reveal component

**Impact:** Low (prep work)  
**Effort:** ~45 minutes  
**Files:** New `components/scroll-reveal.tsx` (**proposed — this file does not exist yet**), `globals.css`

Reusable IntersectionObserver-based reveal for future landing page sections.

#### Prompt

```
Create a reusable ScrollReveal component for the qp-gen app.

Requirements:
1. Create `frontend/components/scroll-reveal.tsx` with a `ScrollReveal` component using IntersectionObserver:
   - `threshold: 0.15` (trigger at 15% visible)
   - `rootMargin: "0px 0px -50px 0px"`
   - Once triggered, adds class that plays reveal animation
   - `once: true` — don't re-hide on scroll up
2. Reveal animation: `opacity: 0, translateY(24px)` → `opacity: 1, translateY(0)`, 0.6s, ease `[0.22, 1, 0.36, 1]`
3. Support staggered children: each child delays by 80ms from previous
4. Add `@keyframes scroll-reveal` in `globals.css`
5. Respect `prefers-reduced-motion` — content visible immediately, no animation
6. Clean up observer on unmount
7. Export as both a wrapper component `<ScrollReveal>` and a hook `useScrollReveal()`
```

---

### 7. Dashboard home state

**Impact:** High  
**Effort:** ~3 hours  
**Files:** `app/(dashboard)/dashboard/page.tsx`, `lib/api-client.ts`

Add an overview/home view to the dashboard that shows before the user starts chatting. Currently the dashboard drops directly into an empty AI chat prompt.

#### Prompt

```
Add a dashboard home state to the qp-gen app that shows an overview before the user starts chatting.

Current state:
- `frontend/app/(dashboard)/dashboard/page.tsx` — the dashboard is entirely the AI chat. On load, the user sees:
  - A ChatBackdrop (Grainient WebGL shader, sand tones)
  - A PromptInputBox at the bottom
  - 4 hardcoded suggestion chips: "Make a class 10 Science unit test on Light.", etc.
  - A conversation sidebar (toggle with PanelLeft icon)
  - When generation runs: PressCheck visualization, then redirect to editor
  - NEW: PaperDesignPanel and usePaperDesign hook (recently merged from feat/general-instructions-designer)
- `frontend/lib/api-client.ts` — has `fetchPapers()`, `fetchProjectsWithQuestions()`, `fetchBankSummary()` for data
- Navigation: Dashboard, Question Bank → /paper-library, Editor, Papers → /question-bank, Builder → /build-paper, Settings
- The user lands on `/dashboard` after login. There's no summary of their work — just a blank chat.

Requirements:
1. Add a "home" state that shows BEFORE the user sends their first message or selects a conversation. Once they start chatting, the home state fades out and the full chat takes over (existing behavior)
2. The home state should include:
   - A greeting: "Good [morning/afternoon/evening], [userName]" — use the session user data already available via `useSession()`
   - Recent papers section: last 3-5 papers from `fetchPapers()`, each showing title, subject, class, and a relative timestamp. Clicking one navigates to the editor with that paper loaded
   - Quick stats row: total papers count, total questions in bank (from `fetchBankSummary()`), displayed as simple number + label cards
   - Quick action buttons: "Generate a paper" (scrolls to / focuses the prompt box), "Build from bank" (navigates to `/build-paper`), "Browse papers" (navigates to `/question-bank`)
3. The PromptInputBox should remain visible at the bottom in both home and chat states — it's the constant element
4. The ChatBackdrop Grainient should remain visible behind the home state (it's decorative)
5. The conversation sidebar toggle should still work from the home state
6. Animate the home state entrance: staggered fade-in for each section (greeting, recent papers, stats, actions), 80ms stagger, same ease as existing follow-up cards `[0.22, 1, 0.36, 1]`
7. When transitioning from home → chat (user sends first message), the home state should fade out: `opacity 1→0, y 0→-12` over 200ms, then unmount
8. Data fetching: use `useEffect` + `useState` with loading skeletons. If fetch fails, the home state still shows the greeting and action buttons — stats and recent papers degrade gracefully to empty
9. Respect the existing `SUGGESTIONS` array for the suggestion chips — keep them on the home state, positioned near the prompt box
10. The home state is NOT a separate route — it's a conditional render within the existing dashboard page based on whether a conversation is active

Don't restructure the chat flow, the PressCheck generation, the PaperDesignPanel, or the conversation management. The home state is additive — it layers on top when no conversation is selected.
```

---

### 8. Rich empty states with CTAs

**Impact:** Medium  
**Effort:** ~1 hour  
**Files:** `app/(dashboard)/question-bank/page.tsx`, `app/(dashboard)/paper-library/page.tsx`

The empty states now have breathing icons (shipped in `cceebf4`) but still lack guidance for new users. Upgrade them with headlines, subtitles, and CTA buttons.

#### Prompt

```
Upgrade the empty states on the Papers and Question Bank pages with headlines, subtitles, and call-to-action buttons.

Current state:
- `frontend/app/(dashboard)/question-bank/page.tsx` — the Papers page. Empty state has a dashed border container with a Lucide icon (FileText) that now has the `empty-breathe` CSS animation class (4s pulse, added in commit cceebf4). Text says "No saved papers yet" or similar. No CTA button.
- `frontend/app/(dashboard)/paper-library/page.tsx` — the Question Bank page. Similar empty state with a Lucide icon (ListChecks). Text says "No questions" or similar. No CTA button.
- `frontend/app/globals.css` already has `@keyframes empty-breathe` and `.empty-breathe` class.
- The dashboard at `/dashboard` is where users go to generate papers via the AI chat.
- The builder at `/build-paper` lets users build papers from the question bank.
- Both pages use Tailwind for styling, `cn()` for conditional classes, `lucide-react` for icons.

Requirements:
1. For the Papers page (`question-bank/page.tsx`) empty state:
   - Icon: keep existing FileText icon with `empty-breathe` class, but make it larger (h-12 w-12) and use `text-muted-foreground/40` color
   - Headline: "No papers yet" — text-lg font-medium text-foreground
   - Subtitle: "Generate your first paper with the AI assistant, or build one from your question bank." — text-sm text-muted-foreground, max-w-sm, text-center
   - Primary CTA: "Generate a paper" button → navigates to `/dashboard` — use the existing Button component with default variant, with a Sparkles or Zap icon
   - Secondary CTA: "Build from bank" text link → navigates to `/build-paper` — text-sm text-muted-foreground underline
   - Stack vertically, centered, with appropriate gaps (gap-3 between icon/headline/subtitle, gap-4 before buttons)

2. For the Question Bank page (`paper-library/page.tsx`) empty state:
   - Icon: keep existing ListChecks icon with `empty-breathe` class, larger (h-12 w-12), `text-muted-foreground/40`
   - Headline: "No questions in the bank"
   - Subtitle: "Questions are added automatically when you generate a paper. Each chapter's question pool is saved here for re-use."
   - Primary CTA: "Generate your first paper" → `/dashboard`
   - No secondary CTA needed
   - Same layout pattern as above

3. Both empty states should fade in on mount: wrap the container in a `<div>` with `animate-in fade-in duration-500` (Tailwind animate) or use the existing `landing-fade` keyframe
4. Keep the existing dashed border container styling — just enrich the content inside it
5. Buttons should use the existing shadcn Button component from `@/components/ui/button`
6. Use `useRouter` from `next/navigation` for the CTA navigation

Don't change the non-empty state of either page. Don't modify the table, search, filters, or detail panel.
```

---

### 9. Display typeface for headings

**Impact:** Medium  
**Effort:** ~1 hour  
**Files:** `app/layout.tsx`, `app/globals.css`, `app/page.tsx`

Add a display/serif face for the landing page title and optionally for major section headings across the app. Gives the brand typographic personality beyond Inter.

#### Prompt

```
Add a display typeface for headings to the qp-gen app, alongside the existing Inter body font.

Current state:
- `frontend/app/layout.tsx` — loads Inter via `next/font/google` as `--font-inter`. Used for both `--font-sans` and `--font-heading` in globals.css.
- `frontend/app/globals.css` — `@theme inline` block maps `--font-sans: var(--font-inter)` and `--font-heading: var(--font-inter)`. The ink/sand palette is in oklch.
- `frontend/app/page.tsx` — landing page. The main heading uses `h1` with class `landing-title`. Currently renders in Inter. The heading text is "papers made easier".
- `frontend/styles/press-check.css` — internally uses `--pc-serif: ui-serif, Georgia, "Times New Roman", Times, serif` and `--pc-mono` for the generation animation, but these don't surface anywhere else.
- The app's personality is "premium education tool" — ink/sand palette, print-shop generation animation, editorial quality. Inter is the right body face but too neutral for display.

Requirements:
1. Choose ONE display face from these candidates (or pick a better one that fits the ink/sand editorial aesthetic):
   - **DM Serif Display** — warm, transitional serif. Matches the sand palette's warmth. Good at large sizes.
   - **Playfair Display** — high-contrast didone. More editorial/magazine feel. Pairs well with Inter.
   - **Instrument Serif** — modern, slightly quirky. Lighter weight than Playfair.
   - **Space Grotesk** — geometric sans alternative if serif feels wrong. Has personality Inter lacks.
2. Load the chosen font via `next/font/google` in `app/layout.tsx`, alongside the existing Inter import. Set it as a CSS variable `--font-display`
3. Update `app/globals.css`:
   - Change `--font-heading: var(--font-inter)` to `--font-heading: var(--font-display)`
   - Or keep `--font-heading` as Inter and add `--font-display` as a separate variable for selective use
4. Apply the display face to:
   - The landing page `h1.landing-title` ("papers made easier")
   - The landing page kicker ("HSAT")
   - Optionally: page titles in the dashboard area (e.g., "Papers", "Question Bank" headings) — but only if it reads well at text-xl/2xl sizes. If not, keep those in Inter.
5. Don't apply the display face to:
   - Body text, labels, nav items, form elements — those stay Inter
   - The editor content — that has its own typography
   - The press-check animation — it has its own font stack
6. Set appropriate `font-weight`, `letter-spacing`, and `line-height` for the display face at each size it's used
7. Test in both light and dark themes — some serifs render differently on dark backgrounds

The font should add personality to 2-3 key moments (landing title, major headings) without changing the rest of the app. Less is more.
```

---

## Execution Order

| Phase | What | Effort | Status | Why this order |
|-------|------|--------|--------|----------------|
| ~~1~~ | ~~Micro-interactions (CSS)~~ | ~~30 min~~ | ✓ DONE | Shipped in `cceebf4` |
| ~~2~~ | ~~Grainient color alignment~~ | ~~15 min~~ | ✓ DONE | Shipped in `cceebf4` |
| ~~3~~ | ~~Fix nav heading~~ | ~~5 min~~ | ✓ DONE | Shipped in `cceebf4` |
| ~~4~~ | ~~Empty state breathing~~ | ~~30 min~~ | ✓ DONE | Shipped in `cceebf4` |
| ~~5~~ | ~~Hardcoded greys → tokens~~ | ~~2 hrs~~ | ✓ DONE | Shipped in `0216c05` |
| 6 | Page transitions | ~2 hrs | TODO | Foundational — sets the motion language for all subsequent work |
| 7 | Wire GooeyNav | ~1.5 hrs | TODO | Signature element. Missing SVG filter is the only real work |
| 8 | Staggered table rows | ~45 min | TODO | Quick win. Same pattern on two pages |
| 9 | List → detail morph | ~2 hrs | TODO | Needs page transitions in place first for coherent feel |
| 10 | Dashboard home state | ~3 hrs | TODO | High UX impact. Independent of animation work |
| 11 | Rich empty states (CTAs) | ~1 hr | TODO | Builds on breathing animation already shipped |
| 12 | Display typeface | ~1 hr | TODO | Brand personality. Independent of everything else |
| 13 | Save celebration | ~1 hr | TODO | Depends on understanding GiftOverlay API. Editor-only |
| 14 | Scroll reveals | ~45 min | TODO | Prep work — useful only when landing page grows |

*Phases 15–24 are new, from the `5996aa4` coverage extension. They are ordered by severity first, then by dependency: 15 and 16 are correctness bugs that make shipped UI unusable or invisible, 17–19 are the token/primitive work everything else has to sit on, and 20–24 are consistency and motion passes that are cheap once those tokens exist.*

| Phase | What | Effort | Status | Why this order |
|-------|------|--------|--------|----------------|
| 15 | `text-white` → `text-primary-foreground` (7 sites) + `brand-kit-card:177` | ~20 min | TODO | Issue 9. Every primary CTA in the editor, Settings, review tray and comparison workspace is at 1.72:1 in dark mode. Cheapest high-severity fix in the document |
| 16 | Kill `animate-shake`; dark-mode elevation for `.doc-page` | ~45 min | TODO | Issues 17 and 16. A dead class on the autosave-failed state, and the A4 sheet has no visible edge on a dark canvas — both are shipped UI that does not work |
| ~~17~~ | ~~Add `--success` / `--warning` token pairs, then map the hardcoded colours~~ | ~3 hrs | ✓ DONE `60ea6a6` | Issue 10. The tokens already existed — only the mapping was needed, so this unblocked 18 and 21 immediately |
| 18 | Finish the loading migration: 14 raw `Loader2` → `<Spinner>`, grid skeleton on Templates, real fallbacks on 3 auth routes | ~1.5 hrs | TODO | Issue 18. The primitives already exist and are well-documented; this is adoption, not design |
| 19 | Declare a z-index scale in `globals.css`; retire `z-[9999]`, the two `z-[60]`s and the inline `zIndex: 60` | ~1 hr | TODO | Issue 13. Do it before phase 20 adds a shared modal shell, so the shell can own the layer |
| 20 | Shared modal shell: move 5 hand-rolled dialogs onto `Dialog`, one theme-aware scrim | ~2.5 hrs | TODO | Issue 12. Delivers enter/exit animation on five surfaces as a side effect, which is why it is cheaper than animating them individually |
| 21 | Retire the Insert-block rainbow; decide the accent policy | ~1.5 hrs | TODO | Issue 11. Needs the phase 17 decision first. Also cleans up the three-scheme toolbar quick actions |
| 22 | Type scale: collapse 14 arbitrary sizes to 3–4 steps; one page-title treatment | ~2.5 hrs | TODO | Issues 14 and 15. Must land **before** phase 12 (display typeface) — a display face applied to eight different title treatments makes the inconsistency louder, not quieter |
| 23 | Reduced-motion holes: `loading-bar`, `GooeyNav.css`, recharts `isAnimationActive`, register eyes | ~45 min | TODO | Issue 19. The GooeyNav part is a hard prerequisite for phase 7 — do not ship a particle burst with no guard |
| 24 | Shared `AuthCard`; consolidate the two eye rigs; delete `cloud-watch-form.tsx` and `RibbonCut.tsx` | ~1.5 hrs | TODO | Issues 20, 21 and Unused Assets. Fixes the width jump in the onboard flow and removes the duplicate copy of the app's signature animation |

**Done: ~3.5 hours of work already shipped (phases 1–5).**  
**Remaining: ~28 hours across 19 items.**

Revised sequencing after the coverage extension:

- **Fix first (~1 hr, phases 15–16).** Two correctness bugs in shipped UI. Nothing depends on them and nothing should ship ahead of them.
- **Foundations (~8 hrs, phases 17–20).** Status tokens, loading adoption, a z-index scale, a shared modal shell. Phases 21, 22 and 24 all get cheaper afterwards, and phase 20 hands three of the animation phases their enter/exit for free.
- **Motion (~6.25 hrs, phases 6–9) + phase 23.** Unchanged in content, but phase 23 is now a prerequisite for phase 7.
- **Consistency and brand (~6.5 hrs, phases 21, 22, 12, 24).** Phase 22 must precede phase 12; phase 21 must follow phase 17.
- **Independent (~5 hrs, phases 10, 11, 13, 14).** Unaffected by any of the above.

The extension did not change what the original 14 phases were worth. It changed the denominator: those phases addressed 4 routes, and the surfaces added here — the editor, templates, blueprint, admin, settings and the four uncovered auth routes — carry most of the app's remaining design debt and all of its dark-mode defects.
