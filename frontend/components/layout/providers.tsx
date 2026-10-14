"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, useEffect } from "react";

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());

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
