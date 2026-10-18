# Frontend

Next.js 16 (App Router) + React 19. Start at the [root README](../README.md)
for the repo map and quickstart.

```bash
npm install
npm run dev          # http://localhost:3000
npm run typecheck    # tsc --noEmit
npm run lint
npm test             # node self-checks in scripts/
npm run build
```

Environment (`.env`): `NEXT_PUBLIC_API_BASE_URL` (baked in at build time),
`NEXT_PUBLIC_AWS_COGNITO_APP_CLIENT_ID` (must match the backend),
`NEXT_PUBLIC_AWS_COGNITO_REGION`.

## Layout

```
app/          routes only — each page composes feature components
features/     one folder per product area (below)
components/
  ui/           shared primitives (shadcn)
  layout/       navbar, protected layout, providers, school switcher
lib/
  api/          every backend call, one module per resource:
                http.ts (fetch + token refresh) · sse.ts · papers · generation ·
                chat · sources · templates · figures · brand · organizations/users
  *.ts          small shared helpers (utils, toasts, subject, scroll, site)
styles/       editor + design-system CSS
scripts/      node self-checks (test-*.mjs); `npm test` runs them all
```

## Features

| Folder | Owns |
|---|---|
| `editor/` | The paper editor: TipTap editor, toolbar, outline, review tray, store. `extensions/` are TipTap nodes (page, pagination engine, header, math); `dialogs/` and `header/` group the rest. Undo/redo rules live in `history.ts` — anything the editor computes itself must go through `markDerived` |
| `generation/` | Generating a paper: the dock, the run hook, SSE reading, paper-design panel; `blueprint/` is the Blueprint Builder |
| `papers/` | Paper preview, ids, drafts (IndexedDB + server sync), save actions |
| `templates/` | Template manager and picker grid |
| `sources/` | HSAT picker, source readiness, PDF upload hooks |
| `question-types/` | The type picker and the generated catalogue module (**generated — do not edit**) |
| `export/` | The single export path to PDF and DOCX, plus S3 upload |
| `auth/` | Login/register/reset forms, auth and Cognito clients |
| `admin/` | Members, invites, domains, roster, usage analytics |
| `dashboard/` | Assistant backdrop, follow-up card, press check |
| `settings/` | Brand kit card |

A feature may import another feature; shared code that several features need
goes in `lib/` or `components/`. Don't add a new top-level folder for something
that belongs to a feature.
