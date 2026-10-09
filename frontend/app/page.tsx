"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import { getAccessToken } from "@/lib/token-storage";

export default function Home() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  useEffect(() => {
    setIsAuthenticated(!!getAccessToken());
    setIsLoading(false);
  }, []);

  return (
    <main className="font-sans relative isolate min-h-dvh overflow-hidden bg-background text-foreground">
      <div className="workspace-backdrop" aria-hidden="true" />

      <div className="relative z-10 flex min-h-dvh flex-col">
        <header className="flex flex-row items-center justify-between gap-4 px-5 pt-6 px-safe pt-safe sm:px-10">
          <div
            className="relative h-9 w-32 shrink-0 sm:h-10 sm:w-40 landing-fade"
            style={{ animationDelay: "80ms" }}
          >
            <Image
              src="/lighttheme.png"
              alt="HSAT logo"
              fill
              sizes="(max-width: 768px) 160px, 220px"
              className="object-contain object-left"
              priority
            />
          </div>

          {!isLoading && !isAuthenticated && (
            <div
              className="flex items-center gap-3 landing-fade"
              style={{ animationDelay: "160ms" }}
            >
              <Link
                href="/login"
                className="rounded-full border border-brand-ink/20 px-4 py-2 text-sm text-brand-ink/80 transition hover:border-brand-ink/50 hover:text-brand-ink"
              >
                Login
              </Link>
              <Link
                href="/register"
                className="rounded-full bg-primary px-4 py-2 text-sm text-primary-foreground transition-colors hover:bg-primary-hover"
              >
                Sign up
              </Link>
            </div>
          )}
        </header>

        <section className="flex flex-1 items-center justify-center px-6 pb-12 text-center">
          <div className="max-w-4xl">
            <p
              className="landing-kicker landing-fade"
              style={{ animationDelay: "240ms" }}
            >
              HSAT QP-Gen
            </p>
            <h1 className="landing-title">papers made easier</h1>
            <p
              className="landing-subtitle landing-fade mx-auto mt-6"
              style={{ animationDelay: "360ms" }}
            >
              QP-Gen by HSAT Edu Solutions: build, review, and export polished question papers in minutes.
            </p>

            <div
              className="landing-fade mt-8"
              style={{ animationDelay: "440ms" }}
            >
              <Link
                href={isAuthenticated ? "/dashboard" : "/login"}
                className="inline-block rounded-full bg-primary px-8 py-3 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary-hover"
              >
                Get started →
              </Link>
            </div>
          </div>
        </section>
      </div>

    </main>
  );
}
