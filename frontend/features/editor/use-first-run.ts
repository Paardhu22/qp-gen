"use client";

/**
 * Has this teacher seen a given surface before?
 *
 * Nothing in the app could answer that. A search for stored `seen`/`onboard`/
 * `tour`/`dismissed` keys returned nothing, which meant a teacher's first
 * session and their five-hundredth rendered identically — so every hint had to
 * be either permanent clutter for experienced users or absent for new ones.
 * This is the missing primitive, not a screen: it exists so guidance elsewhere
 * can be conditional.
 *
 * ## Unknown means seen
 *
 * Storage can be unavailable — a private window, cleared site data, a browser
 * set to block it — and in some contexts the accessor itself throws. Every
 * read and write is wrapped, and any failure resolves to `seen: true`.
 *
 * That default is deliberate and is the whole safety argument. Failing the
 * other way would re-onboard a teacher on every single visit, turning a
 * privacy setting into a permanent nag with no way out. Failing this way costs
 * a first-time teacher one hint. A hint they never see is a small loss; a hint
 * they cannot stop seeing is a broken product.
 *
 * ## Why it starts `true` on the server too
 *
 * `localStorage` does not exist during a server render, and reading it in the
 * first client render would produce markup that disagrees with the server's.
 * So the hook reports `seen: true` until an effect has run, then flips to the
 * stored answer. First-run UI therefore appears a frame late rather than
 * flashing away on hydration — the right way round, since the alternative
 * shows every returning teacher a flicker of onboarding they have dismissed.
 */

import * as React from "react";

const PREFIX = "qpgen:seen:";

/** Namespaced so these never collide with other app storage. */
function storageKey(key: string): string {
  return `${PREFIX}${key}`;
}

function readSeen(key: string): boolean {
  try {
    return window.localStorage.getItem(storageKey(key)) !== null;
  } catch {
    // Blocked or unavailable — treat as seen. See the note above.
    return true;
  }
}

export interface FirstRunState {
  /**
   * `true` when this surface has been marked seen, when storage is
   * unavailable, or before the first effect has run. Show first-run UI on
   * `!seen`.
   */
  seen: boolean;
  /** Record this surface as seen. Safe to call more than once. */
  markSeen: () => void;
}

export function useFirstRun(key: string): FirstRunState {
  // Starts `true` so server and first client render agree — see above.
  const [seen, setSeen] = React.useState(true);

  React.useEffect(() => {
    setSeen(readSeen(key));
  }, [key]);

  const markSeen = React.useCallback(() => {
    setSeen(true);
    try {
      window.localStorage.setItem(storageKey(key), new Date().toISOString());
    } catch {
      // The state above already flipped, so the surface dismisses for this
      // session even when nothing can be persisted.
    }
  }, [key]);

  return { seen, markSeen };
}

/**
 * Clear every first-run marker. Not wired to UI — it exists so the state is
 * reachable again for testing without hand-editing storage from devtools.
 */
export function resetAllFirstRun(): void {
  try {
    const doomed: string[] = [];
    for (let i = 0; i < window.localStorage.length; i += 1) {
      const k = window.localStorage.key(i);
      if (k && k.startsWith(PREFIX)) doomed.push(k);
    }
    doomed.forEach((k) => window.localStorage.removeItem(k));
  } catch {
    // Nothing stored means nothing to clear.
  }
}
