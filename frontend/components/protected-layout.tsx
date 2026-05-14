"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useSession } from "@/lib/auth-client";

export function ProtectedLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { data, isLoading } = useSession();

  useEffect(() => {
    if (!isLoading && !data?.user) {
      router.replace("/login");
    }
  }, [data?.user, isLoading, router]);

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-zinc-950 text-zinc-400">
        Checking your session...
      </div>
    );
  }

  if (!data?.user) {
    return (
      <div className="flex h-screen items-center justify-center bg-zinc-950 text-zinc-400">
        Redirecting to login...
      </div>
    );
  }

  return <>{children}</>;
}
