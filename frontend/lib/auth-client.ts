"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError, fetchJson } from "@/lib/api-client";
import { clearTokens, getRefreshToken, setTokens } from "@/lib/token-storage";
import { resetEditorStoreForAccountSwitch } from "@/store/editor-store";

// Local helper: wipe every per-account caches that aren't already cleared
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

type SessionUser = {
  id: string;
  name: string;
  email: string;
  image?: string | null;
};

type SessionData = {
  user: SessionUser;
};

type AuthResponse = {
  user: SessionUser;
  accessToken: string;
  refreshToken: string;
  accessTokenExpiresAt: string;
  refreshTokenExpiresAt: string;
};

type RefreshResponse = {
  accessToken: string;
  refreshToken: string;
  accessTokenExpiresAt: string;
  refreshTokenExpiresAt: string;
};

type FetchCallbacks = {
  onSuccess?: () => void;
  onError?: (ctx: { error: { message: string } }) => void;
};

let cachedSession: SessionData | null = null;
let sessionLoaded = false;
let sessionPromise: Promise<SessionData | null> | null = null;
let refreshPromise: Promise<boolean> | null = null;

function resetSessionCache(): void {
  cachedSession = null;
  sessionLoaded = false;
  sessionPromise = null;
  refreshPromise = null;
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
      // empty tray. Doing it post-login risks a frame where the new user is
      // authenticated but still looking at the previous user's data.
      await clearLocalUserState();
      const response = await fetchJson<AuthResponse>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
        skipAuth: true,
        timeoutMs: 30000,
      });
      setTokens({
        accessToken: response.accessToken,
        refreshToken: response.refreshToken,
        accessTokenExpiresAt: response.accessTokenExpiresAt,
        refreshTokenExpiresAt: response.refreshTokenExpiresAt,
      });
      resetSessionCache();
      fetchOptions?.onSuccess?.();
    } catch (error: any) {
      const message =
        error instanceof ApiError
          ? error.message
          : "Unable to reach the server. Please check the backend and try again.";
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
      const response = await fetchJson<AuthResponse>("/api/auth/register", {
        method: "POST",
        body: JSON.stringify({ email, password, name }),
        skipAuth: true,
        timeoutMs: 30000,
      });
      setTokens({
        accessToken: response.accessToken,
        refreshToken: response.refreshToken,
        accessTokenExpiresAt: response.accessTokenExpiresAt,
        refreshTokenExpiresAt: response.refreshTokenExpiresAt,
      });
      resetSessionCache();
      fetchOptions?.onSuccess?.();
    } catch (error: any) {
      const message =
        error instanceof ApiError
          ? error.message
          : "Unable to reach the server. Please check the backend and try again.";
      fetchOptions?.onError?.({ error: { message } });
    }
  },
};

export async function signOut({
  fetchOptions,
}: { fetchOptions?: FetchCallbacks } = {}) {
  try {
    await fetchJson("/api/auth/logout", {
      method: "POST",
    });
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
  // Always treated as success by the API for account-enumeration resistance,
  // but we still surface network/server failures here so the UI doesn't
  // mistakenly tell the user "check your email" when the request never
  // reached the backend.
  try {
    const response = await fetchJson<{ success: boolean; message: string }>(
      "/api/auth/forgot-password",
      {
        method: "POST",
        body: JSON.stringify({ email }),
        skipAuth: true,
        timeoutMs: 30000,
      },
    );
    return { ok: true, message: response.message };
  } catch (error: any) {
    return {
      ok: false,
      message:
        error instanceof ApiError
          ? error.message
          : "Unable to reach the server. Please try again.",
    };
  }
}

export async function resetPassword(
  token: string,
  newPassword: string,
): Promise<{ ok: boolean; message: string }> {
  try {
    await fetchJson<{ success: true }>("/api/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({ token, newPassword }),
      skipAuth: true,
      timeoutMs: 30000,
    });
    return { ok: true, message: "Password updated. You can now sign in." };
  } catch (error: any) {
    return {
      ok: false,
      message:
        error instanceof ApiError
          ? error.message
          : "Unable to reach the server. Please try again.",
    };
  }
}

async function refreshAccessToken(): Promise<boolean> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;

  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    try {
      const response = await fetchJson<RefreshResponse>("/api/auth/refresh", {
        method: "POST",
        body: JSON.stringify({ refreshToken }),
        skipAuth: true,
      });

      setTokens({
        accessToken: response.accessToken,
        refreshToken: response.refreshToken,
        accessTokenExpiresAt: response.accessTokenExpiresAt,
        refreshTokenExpiresAt: response.refreshTokenExpiresAt,
      });
      return true;
    } catch {
      clearTokens();
      resetSessionCache();
      return false;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
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
  // PERF: initialize from the module-level cache synchronously. After the
  // very first session fetch in the app's lifetime, every subsequent
  // protected-route navigation gets `data` populated and `isLoading=false`
  // on the FIRST render — no spinner flash, no extra render cycle. Before
  // this, useState started with `data=null, isLoading=true` even on cache
  // hit, so ProtectedLayout rendered the spinner once and then re-rendered
  // children, which added a perceptible flicker to every navigation and
  // gated the protected layout on a render cycle.
  const [data, setData] = useState<SessionData | null>(
    sessionLoaded ? cachedSession : null,
  );
  const [isLoading, setIsLoading] = useState(!sessionLoaded);
  const [error, setError] = useState<Error | null>(null);

  const fetchSession = useCallback(async () => {
    // If the cache is already hot, skip the loading-state flip — the
    // initial values above are correct and any flip would trigger a
    // pointless re-render of every ProtectedLayout subtree.
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

  // Explicit refresh: always bypasses the module-level cache so fresh
  // data (e.g. updated tokens_consumed) is fetched from the server.
  const forceRefresh = useCallback(async () => {
    resetSessionCache();
    await fetchSession();
  }, [fetchSession]);

  useEffect(() => {
    // Skip the redundant fetch on cache hit — initial state is already
    // populated from `cachedSession`, and another fetchSession() round
    // would only add a wasted HTTP profile call per navigation. The
    // explicit `forceRefresh` path remains for callers that need fresh
    // data (e.g. after token consumption).
    if (sessionLoaded) return;
    fetchSession();
  }, [fetchSession]);

  return { data, isLoading, error, refresh: forceRefresh };
}
