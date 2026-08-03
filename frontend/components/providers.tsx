"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, useEffect } from "react";

import { generationRunner } from "@/lib/generation-runner";

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());

  // A generation outlives the page that started it: the run belongs to a
  // worker thread on the server, not to this tab. So on load we ask what is
  // still running and reattach to it, replaying anything missed while the tab
  // was gone. Without this a reload mid-generation looks exactly like the work
  // having been thrown away — which is what it used to be.
  useEffect(() => {
    void generationRunner.reconcileOnLoad();
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
