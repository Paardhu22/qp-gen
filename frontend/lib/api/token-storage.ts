"use client";

const ACCESS_TOKEN_KEY = "qpgen_access_token"; // We store the ID Token here for Django compatibility
const COGNITO_ACCESS_TOKEN_KEY = "qpgen_cognito_access_token"; // We store the Cognito Access Token here
const REFRESH_TOKEN_KEY = "qpgen_refresh_token";
const ACCESS_TOKEN_EXPIRES_KEY = "qpgen_access_token_expires";
const REFRESH_TOKEN_EXPIRES_KEY = "qpgen_refresh_token_expires";

function canUseStorage(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

export function getAccessToken(): string | null {
  if (!canUseStorage()) return null;
  return window.localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getCognitoAccessToken(): string | null {
  if (!canUseStorage()) return null;
  return window.localStorage.getItem(COGNITO_ACCESS_TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  if (!canUseStorage()) return null;
  return window.localStorage.getItem(REFRESH_TOKEN_KEY);
}

/** Epoch ms at which the stored access/ID token stops being accepted, or null. */
export function getAccessTokenExpiresAt(): number | null {
  if (!canUseStorage()) return null;
  const raw = window.localStorage.getItem(ACCESS_TOKEN_EXPIRES_KEY);
  if (!raw) return null;
  const ms = Date.parse(raw);
  return Number.isNaN(ms) ? null : ms;
}

/**
 * Is the stored token expired, or about to be?
 *
 * `skewMs` is the safety margin: a token with less than this much life left
 * counts as expired, because it can die in flight between the check and the
 * server reading it. Callers that are about to *use* the token pass the default;
 * the background watcher passes a larger window so it renews early.
 *
 * A missing expiry stamp reads as expired — a token we can't date is a token we
 * shouldn't trust. (Both Cognito tokens are minted by the same call and share
 * one lifetime, so this one stamp covers the ID token and the access token.)
 */
export function isAccessTokenExpired(skewMs = 60_000): boolean {
  if (!getAccessToken()) return false; // Nothing stored — not "expired", just absent.
  const expiresAt = getAccessTokenExpiresAt();
  if (expiresAt === null) return true;
  return Date.now() + skewMs >= expiresAt;
}

export function setTokens(params: {
  accessToken: string; // This is the ID Token
  cognitoAccessToken?: string; // This is the Access Token
  refreshToken?: string;
  accessTokenExpiresAt: string;
  refreshTokenExpiresAt?: string;
}): void {
  if (!canUseStorage()) return;
  window.localStorage.setItem(ACCESS_TOKEN_KEY, params.accessToken);
  if (params.cognitoAccessToken) {
    window.localStorage.setItem(COGNITO_ACCESS_TOKEN_KEY, params.cognitoAccessToken);
  }
  if (params.refreshToken) {
    window.localStorage.setItem(REFRESH_TOKEN_KEY, params.refreshToken);
  }
  window.localStorage.setItem(ACCESS_TOKEN_EXPIRES_KEY, params.accessTokenExpiresAt);
  if (params.refreshTokenExpiresAt) {
    window.localStorage.setItem(REFRESH_TOKEN_EXPIRES_KEY, params.refreshTokenExpiresAt);
  }
}

export function clearTokens(): void {
  if (!canUseStorage()) return;
  window.localStorage.removeItem(ACCESS_TOKEN_KEY);
  window.localStorage.removeItem(COGNITO_ACCESS_TOKEN_KEY);
  window.localStorage.removeItem(REFRESH_TOKEN_KEY);
  window.localStorage.removeItem(ACCESS_TOKEN_EXPIRES_KEY);
  window.localStorage.removeItem(REFRESH_TOKEN_EXPIRES_KEY);
}
