"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Spinner } from "@/components/ui/spinner";

import { ApiError } from "@/lib/api-client";
import {
  AUTH_EXPIRED_EVENT,
  isPending,
  signOut,
  startTokenRefreshWatcher,
  useSession,
} from "@/lib/auth-client";
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
  // Next.js SSRs this component, and the server has no localStorage, so
  // the initial state must start `false` on both server and client to
  // keep hydration consistent (an initializer that reads localStorage
  // here causes a hydration mismatch — React then discards the whole
  // tree and re-renders client-side, which is what produced the
  // half-painted page on cold loads). Instead we flip the flag in
  // useLayoutEffect, which runs synchronously before the browser paints
  // the hydrated frame, so real users never see the interim spinner.
  const [hasRefreshToken, setHasRefreshToken] = useState(false);
  useLayoutEffect(() => {
    setHasRefreshToken(Boolean(getRefreshToken()));
  }, [data?.user, isLoading, error]);

  // Renew the Cognito tokens ahead of their 1 h expiry for as long as any
  // dashboard route is mounted, so a tab left open over lunch still holds live
  // credentials. Without this the first action after an idle hour 401s, and the
  // calls that read the token directly (sign out, change password) had no
  // recovery path at all.
  useEffect(() => startTokenRefreshWatcher(), []);

  // The refresh token itself can be dead (revoked by a sign-out elsewhere, or
  // past its 30-day life). Renewal has already cleared storage by then, so send
  // the user to /login rather than leave them on a page where nothing works.
  useEffect(() => {
    const onExpired = () => router.replace("/login");
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired);
  }, [router]);

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
    if (isPending(data.user)) {
      return <PendingApprovalNotice />;
    }
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

  // Everything that reaches here is waiting on the session check — whether it
  // is still in flight or has already timed out into the redirect above. Both
  // states show the same thing, so they share one branch.
  return (
    <div className="flex h-dvh items-center justify-center bg-background">
      <Spinner size="page" />
    </div>
  );
}

function PendingApprovalNotice() {
  const router = useRouter();

  const handleSignOut = async () => {
    await signOut({ fetchOptions: { onSuccess: () => router.push("/login") } });
  };

  return (
    <div className="flex h-dvh flex-col items-center justify-center gap-3 bg-background px-4 text-center">
      <h1 className="text-xl font-semibold text-foreground">Waiting for approval</h1>
      <p className="max-w-sm text-sm text-muted-foreground">
        Your account is set up, but your school admin still needs to approve you before you can start
        generating papers. Check back soon.
      </p>
      <button
        type="button"
        onClick={handleSignOut}
        className="mt-2 text-sm text-muted-foreground underline underline-offset-4 hover:text-foreground"
      >
        Sign out
      </button>
    </div>
  );
}
