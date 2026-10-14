/**
 * How a paper's masthead prints: the logo's size and place, and the date.
 *
 * Shared by the header node, which draws it, and the Word export, which
 * rebuilds it — so the two cannot disagree.
 *
 * Logos come in every shape. Sizing one by WIDTH, as the header used to, made a
 * wide wordmark a sliver and a tall emblem a tower. A logo is sized by its
 * HEIGHT instead and capped in width, so every shape reads at the same weight.
 *
 * Pure, so `scripts/test-header-logo.mjs` can check it without a browser.
 */

export type LogoSide = "left" | "right" | "top";
export type LogoAlign = "auto" | LogoSide;

/** Printed logo heights, in px on the 794px A4 page. */
export const LOGO_HEIGHTS = { small: 48, medium: 64, large: 88 } as const;
export const DEFAULT_LOGO_HEIGHT = LOGO_HEIGHTS.medium;

/** Widest a logo may print, beside the title and above it. */
const MAX_LOGO_WIDTH: Record<LogoSide, number> = { left: 170, right: 170, top: 320 };

/**
 * A logo at least this much wider than tall is a wordmark: beside the title it
 * would squeeze the school's name into a narrow column, so "auto" puts it on top.
 */
export const WORDMARK_RATIO = 2.2;

export function resolveLogoSide(align: unknown, ratio: number | null): LogoSide {
  if (align === "left" || align === "right" || align === "top") return align;
  return ratio !== null && ratio >= WORDMARK_RATIO ? "top" : "left";
}

/** The printed box for a logo of aspect `ratio` (width / height). */
export function fitLogo(ratio: number, height: number, side: LogoSide) {
  const width = Math.min(MAX_LOGO_WIDTH[side], height * ratio);
  return { width: Math.round(width), height: Math.round(width / ratio) };
}


/**
 * The paper's date as printed ("04 Oct 2026"). Stored as an ISO day so the
 * value is timezone-neutral; formatted in the viewer's locale.
 */
export function formatPaperDate(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  try {
    return new Intl.DateTimeFormat(undefined, {
      day: "2-digit",
      month: "short",
      year: "numeric",
    }).format(d);
  } catch {
    return d.toDateString();
  }
}
