"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, useEffect } from "react";

import { generationRunner } from "@/lib/generation-runner";

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());

  // A run is persisted so it survives navigation, but the stream that feeds it
  // cannot survive a reload — it is a POST whose generator runs inside the
  // Django request. So on a fresh load the persisted run is a ghost: the
  // tracker would report a paper being written by nothing. Clear it before any
  // surface renders it.
  //
  // This is the honest behaviour until the backend `GenerationRun` lands; at
  // that point this becomes "reattach to the run" rather than "forget it".
  useEffect(() => {
    generationRunner.reconcileOnLoad();
  }, []);

  // Global theme init. The theme is only otherwise applied by
  // curtain-theme-toggle when it's mounted (Settings/navbar), so a hard
  // refresh on any other page dropped back to light. Providers wraps every
  // page, so re-applying the persisted `.dark` class here fixes that.
  // Auth pages force light via html[data-auth-page] CSS regardless.
  useEffect(() => {
    try {
      if (localStorage.getItem("theme") === "dark") {
        document.documentElement.classList.add("dark");
      }
    } catch {}
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
}
