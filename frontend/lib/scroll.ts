"use client";

/**
 * Scrolling that respects `prefers-reduced-motion`.
 *
 * Smooth scrolling is the canonical vestibular trigger — a whole page sliding
 * under a stationary cursor is the exact motion the preference exists to stop,
 * and it is worse than an animation because the user asked for it and cannot
 * look away from the result. WCAG 2.3.3 treats it as non-essential: the point
 * of jumping to a heading is arriving at the heading, and an instant jump
 * arrives just as well.
 *
 * The app had three unconditional `behavior: "smooth"` calls — the outline
 * panel and two in the editor — while every *decorative* animation on the
 * branch was already correctly scoped to `no-preference`. So the ornament
 * honoured the preference and the one motion that can make someone ill did
 * not.
 *
 * ## Why this is read at call time
 *
 * Not cached, and not a hook. The preference is an OS-level setting a user can
 * change while the tab is open — usually *because* something on screen is
 * making them uncomfortable — and a value captured at mount would keep
 * scrolling smoothly for the rest of the session. `matchMedia` is cheap; a
 * scroll is a user action, not a render.
 */

/** True when the user has asked for less motion. False during SSR. */
export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * `"auto"` when the user has asked for less motion, `"smooth"` otherwise.
 *
 * Spread into any `scrollIntoView` / `scrollTo` options object rather than
 * hardcoding `behavior: "smooth"`.
 */
export function scrollBehavior(): ScrollBehavior {
  return prefersReducedMotion() ? "auto" : "smooth";
}

/**
 * `scrollIntoView`, with the behaviour resolved from the preference.
 *
 * Takes the same options minus `behavior`, which it supplies. Tolerates a null
 * element so callers that resolve a node optionally do not each need a guard.
 */
export function scrollIntoView(
  element: Element | null | undefined,
  options: Omit<ScrollIntoViewOptions, "behavior"> = {},
): void {
  element?.scrollIntoView({ ...options, behavior: scrollBehavior() });
}
