/** A school's brand kit: logos and header branding. */
"use client";

import { fetchForm, fetchJson } from "@/lib/api/http";

export interface BrandAsset {
  id: string;
  name: string;
  kind: string;
  /**
   * The app's own stable `/media/...` URL, minted per read. Never a presigned
   * S3 link — a saved paper outlives any signature, and never a direct bucket
   * URL either: html2canvas taints the canvas on a cross-origin image and the
   * whole PDF export fails.
   */
  url: string;
  width: number | null;
  height: number | null;
}

export interface BrandKit {
  instituteName: string;
  instituteAddress: string;
  accentColor: string;
  fontFamily: string;
  headerLayout: Record<string, unknown>;
  logos: BrandAsset[];
}

/** Reads the kit, creating an empty one server-side on first touch. */
export async function fetchBrandKit(): Promise<BrandKit> {
  const data = await fetchJson<{ brandKit: BrandKit }>("/api/auth/brand-kit", {
    method: "GET",
  });
  return data.brandKit;
}

/** Updates only the fields present in `body`; everything else is left alone. */
export async function updateBrandKit(body: {
  instituteName?: string;
  instituteAddress?: string;
  accentColor?: string;
  fontFamily?: string;
  headerLayout?: Record<string, unknown>;
}): Promise<BrandKit> {
  const data = await fetchJson<{ brandKit: BrandKit }>("/api/auth/brand-kit", {
    method: "PATCH",
    body: JSON.stringify(body),
  });
  return data.brandKit;
}

/** Uploads a logo to the brand kit, so the next paper already has it. */
export async function uploadBrandLogo(
  file: File,
  name?: string,
): Promise<BrandAsset> {
  const form = new FormData();
  form.append("file", file);
  if (name) form.append("name", name);
  const data = await fetchForm<{ asset: BrandAsset }>(
    "/api/auth/brand-kit/assets",
    form,
  );
  return data.asset;
}

export async function renameBrandLogo(
  assetId: string,
  name: string,
): Promise<BrandAsset> {
  const data = await fetchJson<{ asset: BrandAsset }>(
    `/api/auth/brand-kit/assets/${assetId}`,
    { method: "PATCH", body: JSON.stringify({ name }) },
  );
  return data.asset;
}

export async function deleteBrandLogo(assetId: string): Promise<void> {
  await fetchJson<void>(`/api/auth/brand-kit/assets/${assetId}`, {
    method: "DELETE",
  });
}
