/**
 * Fetching an image's bytes for an export (PDF, Word).
 *
 * Both exporters have to read an image's pixels in the browser, so the fetch
 * has to be CORS-clean. The app's `/media/<path>` URL is not, on S3 storage: it
 * answers with a redirect to a presigned S3 URL, and after a cross-origin
 * redirect the browser asks S3 with `Origin: null`. A bucket whose CORS rule
 * names the app's origin sends no CORS headers back, the fetch is blocked, and
 * the image used to be left out of the file without a word — the institute's
 * logo and every figure, blank.
 *
 * `/media/…?inline=1` asks the backend for the bytes themselves (it streams
 * images, behind the CORS rule that already allows this frontend). The plain
 * URL is the fallback, so an older backend that ignores the parameter, or an
 * image the backend declines to stream, behaves exactly as before.
 */

/** URLs that could not be loaded since the last `resetImageFailures()`. */
let failed: string[] = [];

/** The app's own `/media/` URL asked for as bytes; anything else unchanged. */
export function inlineMediaUrl(url: string): string {
  if (!url || url.startsWith("data:") || url.startsWith("blob:")) return url;
  // Our own media route only: relative, or on the API origin.
  if (!/^(?:https?:\/\/[^/?#]+)?\/media\//.test(url)) return url;
  // Already asked, or a presigned URL (a parameter would void its signature).
  if (/[?&](?:inline=|X-Amz-|Signature=)/i.test(url)) return url;
  return url + (url.includes("?") ? "&" : "?") + "inline=1";
}

/** The image's bytes, or null (and a recorded failure) if it cannot be read. */
export async function fetchImageBlob(url: string): Promise<Blob | null> {
  const candidates = Array.from(new Set([inlineMediaUrl(url), url]));
  for (const candidate of candidates) {
    try {
      // "same-origin" credentials: media needs no cookie, and a split-origin
      // deploy rejects credentialed requests without an explicit allow header.
      const response = await fetch(candidate, { mode: "cors", credentials: "same-origin" });
      if (response.ok) return await response.blob();
    } catch {
      // Blocked or unreachable: try the next form of the URL.
    }
  }
  failed.push(url);
  console.warn(`[export] could not load image: ${url}`);
  return null;
}

/** Forget earlier failures — call at the start of an export. */
export function resetImageFailures(): void {
  failed = [];
}

/** The distinct images that could not be loaded since the last reset. */
export function takeImageFailures(): string[] {
  return Array.from(new Set(failed));
}
