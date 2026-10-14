/**
 * The single definition of where the Django API lives.
 *
 * This used to be copy-pasted into three modules (`api-client`, `float-image`,
 * and a since-deleted `auth-refresh`) with a hard-coded EC2 IP as the fallback,
 * which was a trap in two directions:
 *
 *   * `NEXT_PUBLIC_*` is inlined at BUILD time, not read at runtime. A
 *     production build that ran without `NEXT_PUBLIC_API_BASE_URL` set baked
 *     `http://<ip>:8000` into the bundle — and an https:// page cannot make
 *     http:// requests, so the browser blocks every single API call as mixed
 *     content. The whole app appears dead with only a console warning.
 *   * In local development the same fallback silently pointed a developer with
 *     no `.env` at the *production* database.
 *
 * Both are now impossible: `next.config.ts` fails the production build when the
 * variable is missing, so the fallback below only ever applies in development,
 * where localhost is the right guess anyway.
 */

const CONFIGURED = process.env.NEXT_PUBLIC_API_BASE_URL;

/** Dev-only fallback. Production builds cannot reach this — see next.config.ts. */
const DEV_FALLBACK = "http://localhost:8000";

function resolve(): string {
  const raw = (CONFIGURED || DEV_FALLBACK).trim();
  // A trailing slash would produce "…//api/…" once callers append their paths.
  return raw.endsWith("/") ? raw.slice(0, -1) : raw;
}

export const API_BASE_URL = resolve();

/**
 * Warn once if the configured API origin cannot be reached from this page.
 *
 * An https:// page making http:// requests is blocked by the browser before
 * any request is sent, and the resulting `TypeError: Failed to fetch` says
 * nothing about the cause. Naming it explicitly turns a half-hour of
 * head-scratching into a one-line fix.
 */
if (typeof window !== "undefined") {
  if (window.location.protocol === "https:" && API_BASE_URL.startsWith("http://")) {
    console.error(
      `[api] NEXT_PUBLIC_API_BASE_URL is "${API_BASE_URL}" (insecure) but this ` +
        `page is served over https. The browser will block every API request ` +
        `as mixed content. Set NEXT_PUBLIC_API_BASE_URL to an https:// origin ` +
        `and rebuild — this value is baked in at build time, so changing the ` +
        `environment without rebuilding has no effect.`,
    );
  }
}
