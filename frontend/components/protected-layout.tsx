"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";

import { ApiError } from "@/lib/api-client";
import { useSession } from "@/lib/auth-client";
import { getRefreshToken } from "@/lib/token-storage";

// Max ms we wait for the session check before giving up and redirecting to login
const SESSION_TIMEOUT_MS = 8000;

export function ProtectedLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { data, isLoading, error } = useSession();
  const [timedOut, setTimedOut] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // PERF: detect "previously-logged-in on this device" by sampling the
  // refresh token from localStorage. When present, render the layout
  // shell optimistically while useSession resolves in the background,
  // instead of blocking every cold load on the /api/auth/profile HTTP
  // round-trip (the brief's TOP suspect for app-wide slowness).
  // localStorage is client-only, so initial render (server + first client
  // pass) returns false; the effect flips state on the very first client
  // tick, giving a one-frame spinner that immediately yields to the
  // optimistic shell. The actual session HTTP still runs in useSession;
  // a verified failure (no user) drops us through the /login redirect
  // path below — the optimism is purely about *when* we paint.
  const [hasRefreshToken, setHasRefreshToken] = useState(false);
  useEffect(() => {
    setHasRefreshToken(Boolean(getRefreshToken()));
  }, [data?.user, isLoading, error]);

  // Start a safety-net timer as soon as we begin loading.
  // If the session check never finishes (network hang), we redirect to login.
  useEffect(() => {
    if (isLoading) {
      timerRef.current = setTimeout(
        () => setTimedOut(true),
        SESSION_TIMEOUT_MS,
      );
    } else {
      if (timerRef.current) clearTimeout(timerRef.current);
      setTimedOut(false);
    }
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [isLoading]);

  // Redirect only when auth is actually absent/rejected. Slow or failed
  // network checks should not log out a browser that still has a refresh token.
  useEffect(() => {
    const authRejected = error instanceof ApiError && error.status === 401;
    const noStoredSession = !hasRefreshToken;

    if (
      !data?.user &&
      ((!isLoading && (noStoredSession || authRejected)) ||
        (timedOut && noStoredSession))
    ) {
      router.replace("/login");
    }
  }, [data?.user, error, hasRefreshToken, isLoading, timedOut, router]);

  // Fast path: useSession initialized from its module-level cache (any
  // prior navigation in this session) — render children with no flicker.
  if (data?.user) {
    return <>{children}</>;
  }

  // Optimistic path: still loading, but a refresh token is present in
  // localStorage so the user is almost certainly logged in. Render the
  // children now and let useSession verify in the background. If the
  // verification fails, the redirect effect above kicks in. Children
  // that consume `useSession().data.user` will read `undefined` for one
  // render until the fetch resolves — they already cope with that via
  // the existing `data?.user` guards (see e.g. editor/page.tsx).
  const authRejected = error instanceof ApiError && error.status === 401;
  if (!authRejected && hasRefreshToken && (isLoading || error || timedOut)) {
    return <>{children}</>;
  }

  if (isLoading && !timedOut) {
    return (
      <div className="flex h-dvh items-center justify-center bg-background">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="flex h-dvh items-center justify-center bg-background">
      <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
    </div>
  );
}
