"use client";

import { useLayoutEffect } from "react";

export function AuthThemeScope({ children }: { children: React.ReactNode }) {
  useLayoutEffect(() => {
    const html = document.documentElement;
    const restoreDark =
      html.classList.contains("dark") ||
      html.getAttribute("data-prev-theme") === "dark";

    html.classList.remove("dark");
    html.setAttribute("data-auth-page", "");

    return () => {
      html.removeAttribute("data-auth-page");
      html.removeAttribute("data-prev-theme");
      let saved: string | null = null;
      try {
        saved = localStorage.getItem("theme");
      } catch {
        saved = null;
      }
      const shouldBeDark = saved ? saved === "dark" : restoreDark;
      if (shouldBeDark) html.classList.add("dark");
    };
  }, []);

  return <>{children}</>;
}
