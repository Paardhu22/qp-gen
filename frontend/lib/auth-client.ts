"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError, fetchJson } from "@/lib/api-client";
import {
  clearTokens,
  getRefreshToken,
  getAccessToken,
  getCognitoAccessToken,
  setTokens,
} from "@/lib/token-storage";
import { resetEditorStoreForAccountSwitch } from "@/store/editor-store";
import {
  cognitoSignIn,
  cognitoSignUp,
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
      
      const authResult = await cognitoSignIn(email, password);
      
      setTokens({
        accessToken: authResult.IdToken, // Store ID Token as local access token for profile/endpoints
        cognitoAccessToken: authResult.AccessToken, // Store true Access Token for Cognito calls
        refreshToken: authResult.RefreshToken,
        accessTokenExpiresAt: new Date(Date.now() + authResult.ExpiresIn * 1000).toISOString(),
        refreshTokenExpiresAt: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString(),
      });
      
      resetSessionCache();
      
      // Trigger profile sync with Django backend after Cognito login
      const session = await loadSession();
      if (!session) {
        throw new Error("Could not retrieve user profile from the backend.");
      }
      
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
      
      await cognitoSignUp(email, password, name);
      
      // Auto sign-in after successful registration
      const authResult = await cognitoSignIn(email, password);
      
      setTokens({
        accessToken: authResult.IdToken,
        cognitoAccessToken: authResult.AccessToken,
        refreshToken: authResult.RefreshToken,
        accessTokenExpiresAt: new Date(Date.now() + authResult.ExpiresIn * 1000).toISOString(),
        refreshTokenExpiresAt: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString(),
      });
      
      resetSessionCache();
      
      // Trigger profile sync with Django backend
      const session = await loadSession();
      if (!session) {
        throw new Error("Could not retrieve user profile from the backend.");
      }
      
      fetchOptions?.onSuccess?.();
    } catch (error: any) {
      const message = error?.message || "Sign up failed. Please try again.";
      fetchOptions?.onError?.({ error: { message } });
    }
  },
};

export async function signOut({
  fetchOptions,
}: { fetchOptions?: FetchCallbacks } = {}) {
  try {
    const cognitoAccess = getCognitoAccessToken();
    if (cognitoAccess) {
      await cognitoSignOut(cognitoAccess);
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

export async function resetPassword(
  token: string, // In Cognito, the token from URL is the confirmation code
  newPassword: string,
): Promise<{ ok: boolean; message: string }> {
  try {
    let email = "";
    if (typeof window !== "undefined") {
      email = window.sessionStorage.getItem("forgot_password_email") || "";
      // Fallback: search in query params if session storage is empty
      if (!email) {
        const urlParams = new URLSearchParams(window.location.search);
        email = urlParams.get("email") || "";
      }
    }
    
    if (!email) {
      return {
        ok: false,
        message: "Could not resolve the email address for password reset. Please request another reset link.",
      };
    }

    await cognitoConfirmForgotPassword(email, token, newPassword);
    
    if (typeof window !== "undefined") {
      window.sessionStorage.removeItem("forgot_password_email");
    }
    
    return { ok: true, message: "Password updated successfully." };
  } catch (error: any) {
    return {
      ok: false,
      message: error?.message || "Failed to reset password. Please try again.",
    };
  }
}

async function refreshAccessToken(): Promise<boolean> {
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
