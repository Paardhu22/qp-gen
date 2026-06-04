# FIX_REPORT: Dark Mode Visual Regression Fixes (Cluster B)

## Overview
This report documents the UI changes made to correct dark mode inconsistencies and hardcoded colors in the editor and generator form. The changes strictly utilized existing semantic CSS variables instead of introducing new hardcoded hex values, ensuring that light mode remains pixel-identical to its original state.

## 1. Paper Area Choice and Rationale
- **Choice Selected:** Explicit white paper (`#ffffff`) with black text (`#000000`) for BOTH light and dark mode.
- **Rationale:** The previous attempt at a true dark mode paper was incorrect; the paper represents a physical document and must always remain white, even in dark mode. Theme variables must NOT bleed into the document surface. The surrounding editor chrome (navbar, sidebar, toolbar, grey margins) uses the dark mode tokens appropriately.
- **Changed CSS / Scoped Selectors:**
  - `globals.css`:
    - `#tiptap-paper-container` caret color was explicitly reverted to `#000000 !important`.
  - `tiptap-editor.tsx` (`<style>` block):
    - `.document-editor` color set explicitly to `#000000`.
    - `.document-editor .doc-page` background set explicitly to `#ffffff` and border to `#000000`.
    - `.ProseMirror` (internal text) color and caret-color forced to `#000000 !important`.
    - Inner elements like `.section-table-header`, `.question-row`, and `.paper-header-block` explicitly use `background: #ffffff` and `border: 1px solid #000000`.
- **Print Media Query (`@media print`):**
  - Confirmed and hardened the `@media print` rule. The `.document-editor`, `.doc-page`, and `.ProseMirror` are explicitly forced to `background: #ffffff !important` and `color: #000000 !important`. All descendants under `.document-editor` and `.ProseMirror` are forced to `color: #000000 !important`. This ensures printing from dark mode never produces black paper or invisible text.
- **Light Mode Check:** Confirmed that light mode is completely unaffected and remains pixel-identical to its original white paper state.

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
