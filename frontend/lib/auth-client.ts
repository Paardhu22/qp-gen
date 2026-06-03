"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError, fetchJson } from "@/lib/api-client";
import { clearTokens, getRefreshToken, setTokens } from "@/lib/token-storage";

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
    fetchOptions?.onSuccess?.();
  } catch (error: any) {
    clearTokens();
    resetSessionCache();
    fetchOptions?.onError?.({ error: { message: error.message } });
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
