"use client";

import { useCallback, useEffect, useState } from "react";

import { fetchJson } from "@/lib/api-client";

type SessionUser = {
  id: string;
  name: string;
  email: string;
  image?: string | null;
  email_verified?: boolean;
};

type SessionData = {
  user: SessionUser;
};

type FetchCallbacks = {
  onSuccess?: () => void;
  onError?: (ctx: { error: { message: string } }) => void;
};

export const signIn = {
  email: async ({ email, password, fetchOptions }: { email: string; password: string; fetchOptions?: FetchCallbacks }) => {
    try {
      await fetchJson("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      fetchOptions?.onSuccess?.();
    } catch (error: any) {
      fetchOptions?.onError?.({ error: { message: error.message } });
    }
  },
};

export const signUp = {
  email: async ({ email, password, name, fetchOptions }: { email: string; password: string; name: string; fetchOptions?: FetchCallbacks }) => {
    try {
      await fetchJson("/api/auth/register", {
        method: "POST",
        body: JSON.stringify({ email, password, name }),
      });
      fetchOptions?.onSuccess?.();
    } catch (error: any) {
      fetchOptions?.onError?.({ error: { message: error.message } });
    }
  },
};

export async function signOut({ fetchOptions }: { fetchOptions?: FetchCallbacks } = {}) {
  try {
    await fetchJson("/api/auth/logout", {
      method: "POST",
    });
    fetchOptions?.onSuccess?.();
  } catch (error: any) {
    fetchOptions?.onError?.({ error: { message: error.message } });
  }
}

export function useSession() {
  const [data, setData] = useState<SessionData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const fetchSession = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const user = await fetchJson<SessionUser>("/api/auth/me", { method: "GET" });
      setData({ user });
    } catch (err: any) {
      setData(null);
      if (err?.message && err.message !== "Request failed") {
        setError(err);
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSession();
  }, [fetchSession]);

  return { data, isLoading, error, refresh: fetchSession };
}
