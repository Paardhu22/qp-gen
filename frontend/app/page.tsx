"use client";

import Image from "next/image";
import Link from "next/link";
import { Grainient } from "@/components/ui/grainient";
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
    // The Grainient covers the whole viewport, so the base colour is only ever
    // seen in the instant before WebGL comes up (and permanently on a machine
    // that cannot give us a context). `bg-neutral-950` put near-black there
    // under `text-neutral-900` text — dark on dark, unreadable in exactly the
    // case the fallback exists for. Purple matches what the shader paints.
    <main className="relative min-h-dvh overflow-hidden bg-[#f6edff] text-brand-ink">
      <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
        <Grainient
          color1="#fcfcfc"
          color2="#b39de3"
          color3="#f6edff"
          timeSpeed={0.95}
          colorBalance={0.0}
          warpStrength={1.0}
          warpFrequency={5.0}
          warpSpeed={3.7}
          warpAmplitude={50.0}
          blendAngle={0.0}
          blendSoftness={0.05}
          rotationAmount={350}
          noiseScale={2.0}
          grainAmount={0.1}
          grainScale={2.0}
          grainAnimated={false}
          contrast={1.5}
          gamma={1.55}
          saturation={1.0}
          centerX={0.0}
          centerY={0.0}
          zoom={0.9}
          className="landing-grainient"
        />
      </div>

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
                className="rounded-full bg-brand-ink px-4 py-2 text-sm text-white transition hover:bg-[#333a4d]"
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
              HSAT
            </p>
            <h1 className="landing-title">papers made easier</h1>
            <p
              className="landing-subtitle landing-fade mx-auto mt-6"
              style={{ animationDelay: "360ms" }}
            >
              Build, review, and export polished papers in minutes.
            </p>

            <div
              className="landing-fade mt-8"
              style={{ animationDelay: "440ms" }}
            >
              <Link
                href={isAuthenticated ? "/dashboard" : "/login"}
                className="inline-block rounded-full bg-brand-ink px-8 py-3 text-sm font-semibold text-white transition hover:bg-[#333a4d]"
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
