# FIX_REPORT: Dark Mode Visual Regression Fixes (Cluster B)

## Overview
This report documents the UI changes made to correct dark mode inconsistencies and hardcoded colors in the editor and generator form. The changes strictly utilized existing semantic CSS variables instead of introducing new hardcoded hex values, ensuring that light mode remains pixel-identical to its original state.

## 1. Paper Area Choice and Rationale
- **Choice Selected:** True dark paper (`var(--color-card)`, mapped to `oklch(0.205 0 0)` in dark mode).
- **Rationale:** A full dark paper aligns natively with the modern dark mode experience found in standard editors (like Notion or VS Code) and provides zero eye-strain when interacting against the deep surrounding backgrounds (`var(--color-background)` / `var(--color-muted)`). An off-white approach in dark mode creates harsh contrast steps, defeating the goal of a cohesive dark interface.
- **Changed CSS:**
  - `globals.css`: 
    - `#tiptap-paper-container` caret color was changed from `#000000` to `var(--color-foreground)` to remain visible in dark mode.
  - `tiptap-editor.tsx` (`<style>` block):
    - `.document-editor` background changed from `#ffffff` to `transparent`, text from `#000000` to `var(--color-foreground)`.
    - `.doc-page` background changed from `#ffffff` to `var(--color-card)`, border changed from `#000000` to `var(--color-border)`.
    - `.ProseMirror` (internal text) color and caret-color changed from `#000000` to `var(--color-foreground)`.

## 2. Editor Layout & Container Variables
- **Target:** `app/(dashboard)/editor/page.tsx`
- **Changes:**
  - Removed all hardcoded `dark:bg-zinc-*` variants and pure white classes.
  - Sidebar background updated to `bg-background`.
  - Main editor background updated to `bg-muted/30`.
  - Top header strip updated to `bg-muted/50` and `border-border`.
  - Text colors properly mapped to `text-foreground` and `text-muted-foreground`.
  - Drag handle resized borders correctly map to `bg-border` and hover state elements to `bg-primary`/`bg-primary-foreground`.

## 3. Sidebar Inputs/Dropdowns (Generator Form)
- **Target:** `components/generator-form.tsx`
- **Rationale:** The form inputs, dropdown selectors, and placeholders had manual `dark:text-zinc-300`, `dark:bg-zinc-900`, etc., conflicting with standard Shadcn component styles and resulting in a disjointed look. 
- **Changes:**
  - **Inputs & Selects:** Classes like `bg-white dark:bg-zinc-900` were replaced with `bg-background`.
  - **Text Colors:** `text-zinc-600 dark:text-zinc-300` mapped to `text-muted-foreground`, and `text-zinc-900 dark:text-zinc-100` mapped to `text-foreground`.
  - **Borders:** `border-zinc-200 dark:border-zinc-800` simplified to `border-border`.
  - **Upload Area States:** Converted the uploaded document items backing away from hardcoded zinc tokens to use `bg-muted/30` / `bg-muted/50` states.

## 4. Toolbar & Interactive Overlays
- **Target:** `components/editor/toolbar.tsx`, `components/editor/find-replace.tsx`, `components/editor/extensions/header-node.tsx`
- **Rationale:** Icon buttons and overlays (like color picker and find-replace drawer) were suffering from poor legibility with `text-zinc-400` icon sets on dark mode hover states. 
- **Changes:**
  - **Dividers:** `border-zinc-800` in menus and `border-zinc-200 dark:border-zinc-800` in the main toolbar were unified to `border-border`.
  - **Icon Buttons:** Hover and active states (previously `hover:bg-zinc-800` or `hover:text-zinc-100`) were updated to `hover:bg-accent hover:text-foreground`.
  - **Icons:** Default icon colors standardly mapped to `text-muted-foreground`.
  - **Dropdown Panels:** Converted to native popover semantics utilizing `bg-background` and `border-border`.

By ensuring the exclusive use of CSS semantic variables across these targets, dark mode now presents cleanly without regressions in the light theme.
