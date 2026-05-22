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
  const [data, setData] = useState<SessionData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const fetchSession = useCallback(async () => {
    setIsLoading(true);
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
    fetchSession();
  }, [fetchSession]);

  return { data, isLoading, error, refresh: forceRefresh };
}
