"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError, fetchJson } from "@/lib/api-client";
import {
  clearTokens,
  getAccessToken,
  getCognitoAccessToken,
  getRefreshToken,
  isAccessTokenExpired,
  setTokens,
} from "@/lib/token-storage";
import { resetEditorStoreForAccountSwitch } from "@/store/editor-store";
import { clearBrandHeaderCache } from "@/lib/brand-header";
import {
  cognitoSignIn,
  cognitoSignUp,
  cognitoConfirmSignUp,
  cognitoResendConfirmationCode,
  cognitoRefreshToken,
  cognitoForgotPassword,
  cognitoConfirmForgotPassword,
  cognitoSignOut,
} from "@/lib/cognito-client";

// Local helper: wipe every per-account cache that isn't already cleared
// inside `clearTokens()` / `resetSessionCache()`. The Zustand editor store
// persists the review tray + generator context in localStorage; the IndexedDB
// `qp_gen_editor_db` keeps live editor drafts. Both must be reset before a
// different account signs in on the same browser. Called on signIn, signOut,
// and signUp to cover the three account-switch entry points.
async function clearLocalUserState(): Promise<void> {
  try {
    resetEditorStoreForAccountSwitch();
  } catch {
    // Defensive — never let a clear failure block the auth flow.
  }
  try {
    // The brand kit is cached in a module, outside the store — without this a
    // teacher signing in on a colleague's browser would get their school's
    // crest on the next header.
    clearBrandHeaderCache();
  } catch {
    // Same — best effort.
  }
  if (typeof window === "undefined" || typeof indexedDB === "undefined") return;
  try {
    await new Promise<void>((resolve) => {
      const req = window.indexedDB.deleteDatabase("qp_gen_editor_db");
      req.onsuccess = () => resolve();
      req.onerror = () => resolve();
      req.onblocked = () => resolve();
    });
  } catch {
    // Same — best effort.
  }
}

export type SessionUser = {
  id: string;
  name: string;
  email: string;
  image?: string | null;
  status: "pending" | "approved" | "admin" | "rejected";
};

type SessionData = {
  user: SessionUser;
};

type FetchCallbacks = {
  onSuccess?: () => void;
  onError?: (ctx: { error: { message: string } }) => void;
  /**
   * Called when SignUp succeeded but the account still needs email
   * verification (pool has verification ON → user is UNCONFIRMED). The UI
   * should collect the emailed code and call `confirmSignUp.email`.
   */
  onConfirmationRequired?: (ctx: { email: string }) => void;
};

/**
 * Shared post-credential bootstrap: exchange email+password for Cognito tokens,
 * persist them, reset caches, and sync the Django profile. Used by signIn,
 * the auto-confirm signUp path, and confirmSignUp so the three stay identical.
 * Throws if the backend profile cannot be loaded.
 */
async function establishSession(email: string, password: string): Promise<void> {
  const authResult = await cognitoSignIn(email, password);

  setTokens({
    accessToken: authResult.IdToken, // ID Token → local access token for Django endpoints
    cognitoAccessToken: authResult.AccessToken, // true Access Token for Cognito calls
    refreshToken: authResult.RefreshToken,
    accessTokenExpiresAt: new Date(Date.now() + authResult.ExpiresIn * 1000).toISOString(),
    refreshTokenExpiresAt: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString(),
  });

  resetSessionCache();

  const session = await loadSession();
  if (!session) {
    throw new Error("Could not retrieve user profile from the backend.");
  }
}

let cachedSession: SessionData | null = null;
let sessionLoaded = false;
let sessionPromise: Promise<SessionData | null> | null = null;
let refreshPromise: Promise<boolean> | null = null;

function resetSessionCache(): void {
  cachedSession = null;
  sessionLoaded = false;
  sessionPromise = null;
}

function parseJwt(token: string): any {
  try {
    const base64Url = token.split(".")[1];
    const base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split("")
        .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
        .join("")
    );
    return JSON.parse(jsonPayload);
  } catch (e) {
    return null;
  }
}

export function getCognitoGroups(): string[] {
  const token = getAccessToken(); // We check the ID token
  if (!token) return [];
  const payload = parseJwt(token);
  const groups = payload?.["cognito:groups"] || [];
  return Array.isArray(groups) ? groups : [groups];
}

export function isPending(user?: SessionUser | null): boolean {
  if (user?.status) return user.status === "pending";
  const groups = getCognitoGroups();
  return groups.includes("pending") || (!groups.includes("approved") && !groups.includes("admin"));
}

export function isApproved(user?: SessionUser | null): boolean {
  if (user?.status) return user.status === "approved" || user.status === "admin";
  const groups = getCognitoGroups();
  return groups.includes("approved") || groups.includes("admin");
}

export function isAdmin(user?: SessionUser | null): boolean {
  if (user?.status) return user.status === "admin";
  const groups = getCognitoGroups();
  return groups.includes("admin");
}

export const signIn = {
  email: async ({
    email,
    password,
    fetchOptions,
  }: {
    email: string;
    password: string;
    fetchOptions?: FetchCallbacks;
  }) => {
    try {
      // Wipe any prior account's cached editor state BEFORE the new tokens
      // are written, so the very next render under the new identity sees an
      // empty tray.
      await clearLocalUserState();

      await establishSession(email, password);

      fetchOptions?.onSuccess?.();
    } catch (error: any) {
      const message = error?.message || "Authentication failed. Please check your credentials and try again.";
      fetchOptions?.onError?.({ error: { message } });
    }
  },
};

export const signUp = {
  email: async ({
    email,
    password,
    name,
    fetchOptions,
  }: {
    email: string;
    password: string;
    name: string;
    fetchOptions?: FetchCallbacks;
  }) => {
    try {
      // Fresh account — never bring forward any prior user's persisted state.
      await clearLocalUserState();

      const result = await cognitoSignUp(email, password, name);

      // If the pool requires email verification the user is UNCONFIRMED now;
      // auto sign-in would throw UserNotConfirmedException. Hand off to the UI
      // to collect the emailed code (→ confirmSignUp.email). Only auto sign-in
      // when the pool auto-confirmed the account.
      if (!result.UserConfirmed) {
        if (typeof window !== "undefined") {
          window.sessionStorage.setItem("pending_confirmation_email", email);
        }
        fetchOptions?.onConfirmationRequired?.({ email });
        return;
      }

      await establishSession(email, password);

      fetchOptions?.onSuccess?.();
    } catch (error: any) {
      const message = error?.message || "Sign up failed. Please try again.";
      fetchOptions?.onError?.({ error: { message } });
    }
  },
};

/**
 * Complete email verification for a freshly-registered account, then sign in.
 * `password` is the password the user just chose at sign-up (kept in the form's
 * state) so we can establish the session immediately after confirming.
 */
export const confirmSignUp = {
  email: async ({
    email,
    code,
    password,
    fetchOptions,
  }: {
    email: string;
    code: string;
    password: string;
    fetchOptions?: FetchCallbacks;
  }) => {
    try {
      await clearLocalUserState();

      try {
        await cognitoConfirmSignUp(email, code);
      } catch (confirmError: any) {
        // If the account is already verified (e.g. auto-confirm pool, an admin
        // confirmed it, or a double-submit), Cognito throws
        // NotAuthorizedException "User cannot be confirmed. Current status is
        // CONFIRMED". That's not a failure — skip confirmation and sign in.
        const msg = String(confirmError?.message || "");
        const alreadyConfirmed =
          msg.includes("Current status is CONFIRMED") ||
          msg.includes("User cannot be confirmed");
        if (!alreadyConfirmed) throw confirmError;
      }

      await establishSession(email, password);

      if (typeof window !== "undefined") {
        window.sessionStorage.removeItem("pending_confirmation_email");
      }

      fetchOptions?.onSuccess?.();
    } catch (error: any) {
      const message =
        error?.message || "Account confirmation failed. Check the code and try again.";
      fetchOptions?.onError?.({ error: { message } });
    }
  },
};

/** Re-send the email verification code for an unconfirmed account. */
export async function resendConfirmationCode(
  email: string,
): Promise<{ ok: boolean; message: string }> {
  try {
    await cognitoResendConfirmationCode(email);
    return { ok: true, message: "A new verification code has been sent to your email." };
  } catch (error: any) {
    return {
      ok: false,
      message: error?.message || "Failed to resend the verification code.",
    };
  }
}

export async function signOut({
  fetchOptions,
}: { fetchOptions?: FetchCallbacks } = {}) {
  try {
    // Renew first if the access token is stale: GlobalSignOut is the only call
    // that revokes *other* devices' sessions, and it needs a live access token.
    // Without this, signing out after an idle hour did nothing server-side and
    // logged "NotAuthorizedException: Access Token has expired".
    await ensureFreshTokens();

    const cognitoAccess = getCognitoAccessToken();
    const refresh = getRefreshToken();
    if (cognitoAccess || refresh) {
      await cognitoSignOut(cognitoAccess, refresh);
    }
    clearTokens();
    resetSessionCache();
    await clearLocalUserState();
    fetchOptions?.onSuccess?.();
  } catch (error: any) {
    clearTokens();
    resetSessionCache();
    await clearLocalUserState();
    fetchOptions?.onError?.({ error: { message: error.message } });
  }
}

export async function requestPasswordReset(email: string): Promise<{
  ok: boolean;
  message: string;
}> {
  try {
    await cognitoForgotPassword(email);
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem("forgot_password_email", email);
    }
    return { ok: true, message: "A password reset code has been sent to your email." };
  } catch (error: any) {
    return {
      ok: false,
      message: error?.message || "Failed to request password reset. Please try again.",
    };
  }
}

/**
 * Complete the code-based Cognito password reset: ConfirmForgotPassword with the
 * email, the 6-digit code from the user's inbox, and the new password. `code` is
 * the Cognito ConfirmationCode (Cognito sends a code, not a clickable link).
 * Returns the Cognito exception type as `code` (e.g. CodeMismatchException) so
 * the UI can map it to friendly copy.
 */
export async function resetPassword(
  email: string,
  code: string,
  newPassword: string,
): Promise<{ ok: boolean; message: string; code?: string }> {
  try {
    await cognitoConfirmForgotPassword(email, code, newPassword);

    if (typeof window !== "undefined") {
      window.sessionStorage.removeItem("forgot_password_email");
    }

    return { ok: true, message: "Password updated successfully." };
  } catch (error: any) {
    return {
      ok: false,
      message: error?.message || "Failed to reset password. Please try again.",
      code: error?.name,
    };
  }
}

/**
 * Fired when the refresh token itself is dead (revoked, or past its 30-day
 * life). Tokens have already been cleared by the time this dispatches; the
 * listener's job is to get the user to /login instead of leaving them on a
 * signed-in-looking page where every action fails. See `ProtectedLayout`.
 */
export const AUTH_EXPIRED_EVENT = "qpgen:auth-expired";

function announceAuthExpired(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
}

export async function refreshAccessToken(): Promise<boolean> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;

  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    try {
      const authResult = await cognitoRefreshToken(refreshToken);

      setTokens({
        accessToken: authResult.IdToken,
        cognitoAccessToken: authResult.AccessToken,
        refreshToken: authResult.RefreshToken || refreshToken, // Cognito may not always return a new refresh token
        accessTokenExpiresAt: new Date(Date.now() + authResult.ExpiresIn * 1000).toISOString(),
      });
      return true;
    } catch {
      clearTokens();
      resetSessionCache();
      announceAuthExpired();
      return false;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

/**
 * Renew the tokens if they are expired or nearly so; no-op otherwise.
 *
 * Call this before anything that reads a token *directly* rather than through
 * `fetchJson` — Cognito calls (sign out, change password) and any request that
 * can't cheaply be retried after a 401. Returns false only when there is no
 * usable session left.
 */
export async function ensureFreshTokens(): Promise<boolean> {
  if (!getRefreshToken()) return false;
  // A refresh token with no access token beside it is a half-cleared session
  // (or one restored from an older storage layout) — mint a fresh pair.
  if (getAccessToken() && !isAccessTokenExpired()) return true;
  return refreshAccessToken();
}

// Renew this long before the token actually dies. Cognito tokens live 1 h by
// default, so a 5-minute lead is ~8% of the lifetime — frequent enough that a
// tab is never holding a dead token, rare enough to stay off the network.
const REFRESH_LEAD_MS = 5 * 60 * 1000;
const REFRESH_POLL_MS = 60 * 1000;

let watcherCount = 0;
let watcherTimer: ReturnType<typeof setInterval> | null = null;

/**
 * Keep the session alive for as long as the app is mounted.
 *
 * The refresh used to be purely reactive — something had to eat a 401 first.
 * That leaves two holes this closes: a tab idle past the token's 1 h lifetime
 * wakes up with dead credentials (every panel errors at once until the retries
 * land), and the token-reading calls that never see a 401 at all — sign-out and
 * change-password — simply failed.
 *
 * Polls on a timer *and* on the events that mean "this tab was asleep and is
 * back": timers are throttled or frozen in background tabs, so the timer alone
 * cannot be trusted to have run. Returns a disposer.
 */
export function startTokenRefreshWatcher(): () => void {
  if (typeof window === "undefined") return () => {};

  const check = () => {
    // Nothing to renew, or nothing to renew *with* — stay quiet.
    if (!getRefreshToken() || !getAccessToken()) return;
    if (!isAccessTokenExpired(REFRESH_LEAD_MS)) return;
    void refreshAccessToken();
  };

  watcherCount += 1;
  if (watcherCount === 1) {
    watcherTimer = setInterval(check, REFRESH_POLL_MS);
  }

  const onWake = () => {
    if (document.visibilityState === "visible") check();
  };
  document.addEventListener("visibilitychange", onWake);
  window.addEventListener("focus", check);
  window.addEventListener("online", check);

  check(); // A tab that mounts with an already-stale token shouldn't wait a minute.

  return () => {
    document.removeEventListener("visibilitychange", onWake);
    window.removeEventListener("focus", check);
    window.removeEventListener("online", check);
    watcherCount -= 1;
    if (watcherCount === 0 && watcherTimer) {
      clearInterval(watcherTimer);
      watcherTimer = null;
    }
  };
}

async function loadSession(): Promise<SessionData | null> {
  if (sessionLoaded) return cachedSession;
  if (sessionPromise) return sessionPromise;

  sessionPromise = (async () => {
    try {
      const user = await fetchJson<SessionUser>("/api/auth/profile", {
        method: "GET",
      });
      cachedSession = { user };
      sessionLoaded = true;
      return cachedSession;
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 401) {
        const refreshed = await refreshAccessToken();
        if (refreshed) {
          const user = await fetchJson<SessionUser>("/api/auth/profile", {
            method: "GET",
          });
          cachedSession = { user };
          sessionLoaded = true;
          return cachedSession;
        }
      }

      cachedSession = null;
      sessionLoaded = true;
      throw err;
    } finally {
      sessionPromise = null;
    }
  })();

  return sessionPromise;
}

export function useSession() {
  const [data, setData] = useState<SessionData | null>(
    sessionLoaded ? cachedSession : null,
  );
  const [isLoading, setIsLoading] = useState(!sessionLoaded);
  const [error, setError] = useState<Error | null>(null);

  const fetchSession = useCallback(async () => {
    if (!sessionLoaded) {
      setIsLoading(true);
    }
    setError(null);
    try {
      const session = await loadSession();
      setData(session);
    } catch (err: any) {
      setData(null);
      if (err?.message && err.message !== "Request failed") setError(err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const forceRefresh = useCallback(async () => {
    resetSessionCache();
    await fetchSession();
  }, [fetchSession]);

  useEffect(() => {
    if (sessionLoaded) return;
    fetchSession();
  }, [fetchSession]);

  return { data, isLoading, error, refresh: forceRefresh };
}
