"use client";

/**
 * Building a paper's masthead from the school's brand kit.
 *
 * `defaultHeaderJSON` is a module constant reading "SCHOOL NAME",
 * inserted at four points in the editor. It has to stay a constant — those
 * call sites are synchronous, inside ProseMirror transactions, and cannot wait
 * on a fetch — so the kit is fetched once and cached here instead, and the
 * builder reads the cache.
 *
 * The consequence is deliberate: the very first header inserted in a cold tab
 * may use the fallback, because nothing has loaded yet. That is the right
 * trade. Blocking a paper's first header on a network round trip would make
 * the editor feel broken for the sake of a masthead the teacher can fix by
 * typing, and `primeBrandHeader()` is called on editor mount so the window is
 * a fraction of a second and only ever once per session.
 *
 * An unreachable brand kit must never stop a header being inserted. Every path
 * here falls back to the hardcoded default rather than throwing.
 */

import { fetchBrandKit, type BrandKit } from "@/lib/api-client";
import { defaultHeaderJSON } from "@/components/editor/templates";
import { isGenericPaperTitle } from "@/components/editor/header-details";

let cached: BrandKit | null = null;
let inFlight: Promise<BrandKit | null> | null = null;

/**
 * Load the kit into the cache. Safe to call repeatedly — concurrent callers
 * share one request, and a failure is swallowed so the caller never has to
 * handle branding being unavailable.
 */
export async function primeBrandHeader(): Promise<BrandKit | null> {
  if (cached) return cached;
  if (inFlight) return inFlight;

  inFlight = fetchBrandKit()
    .then((kit) => {
      cached = kit;
      return kit;
    })
    .catch(() => null)
    .finally(() => {
      inFlight = null;
    });

  return inFlight;
}

/** Drop the cache — call on sign-out, so the next account gets its own brand. */
export function clearBrandHeaderCache(): void {
  cached = null;
  inFlight = null;
}

/** The kit as currently cached, or null if it has not loaded (or failed). */
export function cachedBrandKit(): BrandKit | null {
  return cached;
}

function textNode(text: string, level: 1 | 2) {
  return {
    type: "heading",
    attrs: { level },
    content: [{ type: "text", text }],
  };
}

/**
 * A header block reflecting the school's brand, or the hardcoded default when
 * there is no brand to reflect.
 *
 * Only the parts the teacher actually filled in are substituted. A kit with a
 * name but no address replaces the title line and leaves everything else as it
 * was — a half-filled kit must not produce a half-empty masthead.
 */
export function headerJSONFromBrand(metadata: {
  subject?: string; className?: string; examName?: string;
  marks?: string | number; setLabel?: string; time?: string;
} = {}): any {
  const kit = cached;

  const hasName = Boolean(kit?.instituteName?.trim());
  const hasAddress = Boolean(kit?.instituteAddress?.trim());
  const logo = kit?.logos?.[0];

  // Structural clone so a caller mutating the returned node — ProseMirror
  // normalises what it is given — cannot corrupt the template for the next
  // insertion.
  const header = JSON.parse(JSON.stringify(defaultHeaderJSON));

  if (hasName && kit) {
    header.content[0] = textNode(kit.instituteName.trim().toUpperCase(), 1);
  }
  if (hasAddress && kit) {
    header.content.splice(1, 0, {
      type: "paragraph", content: [{ type: "text", text: kit.instituteAddress.trim() }],
    });
  }
  if (logo?.url) {
    // Size and placement are the header's defaults: medium height, and
    // "auto", which puts a wordmark on top and a crest at the side.
    header.attrs = { ...(header.attrs || {}), logoUrl: logo.url };
  }

  if (metadata.examName?.trim()) {
    const title = textNode(metadata.examName.trim(), 2);
    if (!isGenericPaperTitle(title)) header.content.push(title);
  }
  const values: Record<string, string | number | undefined> = {
    subject: metadata.subject, class: metadata.className, marks: metadata.marks,
    set: metadata.setLabel, time: metadata.time,
  };
  header.attrs.details = header.attrs.details.map((field: any) => ({
    ...field, value: values[field.id] == null ? field.value : String(values[field.id]).trim(),
  }));
  return header;
}
