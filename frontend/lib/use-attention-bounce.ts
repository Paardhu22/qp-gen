"use client";

/**
 * "Look here": scroll an element into view and bounce it, once per request.
 *
 * Used when a generation finishes, on the review tray, which sits below the
 * fold in the Studio dock where the teacher is probably not looking. Done on the DOM rather than through state: it is a
 * one-shot effect, and a class swap restarts the animation even when two
 * runs finish back to back.
 *
 * `requestedAt` is a timestamp from the store. Only a request from the last
 * few seconds counts, so a remount (the editor remounts on every set-tab
 * switch) does not replay an old one, while a target that mounts just after
 * the request — a panel opening for it — still gets it. A copy that is not on
 * screen has no offsetParent and is skipped.
 */

import { useEffect, type RefObject } from "react";

const FRESH_FOR_MS = 4000;

export function useAttentionBounce(
  requestedAt: number,
  scrollTarget: RefObject<HTMLElement | null>,
  bounceTarget: RefObject<HTMLElement | null>,
  /** Re-check when the targets may have just mounted. */
  ready = true,
  /** Where the scroll lands: "start" for a tall panel, "nearest" for a small one. */
  block: ScrollLogicalPosition = "start",
) {
  useEffect(() => {
    if (!ready || !requestedAt || Date.now() - requestedAt > FRESH_FOR_MS) return;
    const scroll = scrollTarget.current;
    const bounce = bounceTarget.current;
    if (!scroll || !bounce || scroll.offsetParent === null) return;

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    scroll.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block });

    bounce.classList.remove("attention-bounce");
    void bounce.offsetWidth; // restart the animation
    bounce.classList.add("attention-bounce");
    // Two animations run (bounce, then the longer ring); the class comes off
    // when the ring — the last to finish — ends.
    const done = (event: AnimationEvent) => {
      if (event.animationName === "attention-ring") {
        bounce.classList.remove("attention-bounce");
      }
    };
    bounce.addEventListener("animationend", done);
    return () => bounce.removeEventListener("animationend", done);
  }, [requestedAt, scrollTarget, bounceTarget, ready, block]);
}
