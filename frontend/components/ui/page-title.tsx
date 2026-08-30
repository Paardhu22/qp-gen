/**
 * The `<h1>` of a page, at one size.
 *
 * There were eight page titles in five treatments — `text-sm`, `text-lg`,
 * `text-2xl` and `text-3xl`, in `font-semibold` and `font-bold`, with
 * `tracking-tight` on some and not others — and Settings rendered its title as
 * an `<h2>` with no `<h1>` above it at all.
 *
 * That is worth fixing on its own, but it also blocks something: a display
 * typeface has to be applied to *a* heading scale, and there was no scale to
 * apply it to. Every page routes through here, so that change becomes one
 * edit rather than eight guesses.
 *
 * ## Why `lg` and not something grander
 *
 * The workspace pages — papers, questions, templates — put the title in a
 * dense header row beside filters, counts and buttons, and already used `lg`
 * or smaller. A `3xl` title in that row would not fit. The pages that were
 * larger (Settings, Admin) have room to spare and lose nothing by coming
 * down, so the scale is set by the constraint, not the average.
 *
 * The dashboard chat's "What can I help with?" is deliberately **not** a
 * `PageTitle`. It is a greeting that disappears once a conversation starts,
 * not a label for a place, and it should keep its own hero sizing.
 */

import { cn } from "@/lib/utils";

interface PageTitleProps extends React.ComponentProps<"h1"> {
  /**
   * Render as `<h2>` for a section heading *inside* a page that already has
   * its own `<h1>`. Never use it to avoid an `<h1>` — a page needs one.
   */
  as?: "h1" | "h2";
}

export function PageTitle({
  as: Tag = "h1",
  className,
  ...props
}: PageTitleProps) {
  return (
    <Tag
      className={cn(
        "text-lg font-semibold tracking-tight text-foreground",
        className,
      )}
      {...props}
    />
  );
}
