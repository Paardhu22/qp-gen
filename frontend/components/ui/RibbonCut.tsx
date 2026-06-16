"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { DotLottie } from "@lottiefiles/dotlottie-web";

export interface RibbonCutProps {
  /** Rendered width in px. Also defines the aspect ratio. Defaults to 400. */
  width?: number;
  /** Rendered height in px. Also defines the aspect ratio. Defaults to 100. */
  height?: number;
  /** Fired once, after the ribbon-cut animation has finished playing. */
  onComplete?: () => void;
  className?: string;
}

const SRC = "/animations/Gift.lottie";

// Serve the player's WASM runtime from our own origin instead of the default
// jsDelivr/unpkg CDN, so the ribbon never depends on a third party or a CSP
// allowance at runtime. The file is kept in sync by the `copy-lottie-wasm`
// npm script (runs on predev/prebuild).
let wasmConfigured = false;
function ensureWasmUrl() {
  if (wasmConfigured) return;
  wasmConfigured = true;
  DotLottie.setWasmUrl("/dotlottie-player.wasm");
}

/**
 * A click-to-play ribbon-cut animation rendered onto a <canvas> via dotlottie-web.
 *
 * - Mounts PAUSED on frame 0 (ribbon fully intact, nothing moving).
 * - One click plays the animation exactly once (no loop). Further clicks are ignored.
 * - Calls `onComplete` when the cut finishes, so the parent can reveal what's next.
 */
export default function RibbonCut({
  width = 400,
  height = 100,
  onComplete,
  className,
}: RibbonCutProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const dotLottieRef = useRef<DotLottie | null>(null);
  const onCompleteRef = useRef(onComplete);

  const [isLoaded, setIsLoaded] = useState(false);
  const [hasPlayed, setHasPlayed] = useState(false);

  // Keep the latest callback reachable without re-creating the player instance.
  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    ensureWasmUrl();

    const dotLottie = new DotLottie({
      canvas,
      src: SRC,
      autoplay: false,
      loop: false,
      renderConfig: { autoResize: true },
    });
    dotLottieRef.current = dotLottie;

    const handleLoad = () => setIsLoaded(true);
    const handleComplete = () => {
      setHasPlayed(true);
      onCompleteRef.current?.();
    };

    dotLottie.addEventListener("load", handleLoad);
    dotLottie.addEventListener("complete", handleComplete);

    return () => {
      dotLottie.removeEventListener("load", handleLoad);
      dotLottie.removeEventListener("complete", handleComplete);
      dotLottie.destroy();
      dotLottieRef.current = null;
    };
  }, []);

  const play = useCallback(() => {
    if (!isLoaded || hasPlayed) return;
    dotLottieRef.current?.play();
  }, [isLoaded, hasPlayed]);

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLCanvasElement>) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        play();
      }
    },
    [play],
  );

  const interactive = isLoaded && !hasPlayed;

  return (
    <canvas
      ref={canvasRef}
      onClick={play}
      onKeyDown={handleKeyDown}
      role="button"
      tabIndex={interactive ? 0 : -1}
      aria-label="Cut the ribbon to unwrap the page"
      aria-disabled={!interactive}
      className={className}
      style={{
        width: `${width}px`,
        maxWidth: "100%",
        height: "auto",
        aspectRatio: `${width} / ${height}`,
        cursor: interactive ? "pointer" : "default",
        touchAction: "manipulation",
        outline: "none",
        display: "block",
      }}
    />
  );
}
