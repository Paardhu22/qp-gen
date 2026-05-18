"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";

import { useSession } from "@/lib/auth-client";

// Max ms we wait for the session check before giving up and redirecting to login
const SESSION_TIMEOUT_MS = 8000;

export function ProtectedLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { data, isLoading } = useSession();
  const [timedOut, setTimedOut] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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

  // Redirect when: session check is done (or timed out) and no user found
  useEffect(() => {
    if ((!isLoading || timedOut) && !data?.user) {
      router.replace("/login");
    }
  }, [data?.user, isLoading, timedOut, router]);

  if (isLoading && !timedOut) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!data?.user) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return <>{children}</>;
}
