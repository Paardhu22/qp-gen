"use client";

/**
 * The hue behind the dashboard chat.
 *
 * A `Grainient` field in the theme kit's two colours — purple `#b39de3` warping
 * through white — so the chat sits on something that moves slowly rather than a
 * flat panel. Everything about it is decorative: `styles/grainient.css` masks it
 * out towards the centre where the messages are, drops its opacity, and makes it
 * click-through. It pauses when the tab is hidden and draws a single static
 * frame under `prefers-reduced-motion`.
 *
 * Loaded lazily and client-only. The component is ~7 kB of GLSL plus `ogl`, and
 * it touches `window`/`document` in its first effect — pulling that into the
 * dashboard's server-rendered bundle would delay the chat itself for a
 * background. `ssr: false` also means the first paint is the real UI, not a
 * canvas the client has to reconcile.
 */

import dynamic from "next/dynamic";

const Grainient = dynamic(
  () => import("@/components/ui/grainient").then((m) => m.Grainient),
  { ssr: false },
);

// Purple → white → purple. The middle stop being white is what keeps the field
// mostly canvas with warmth pooling at the edges, instead of a solid wash of
// colour behind the text.
const PURPLE = "#b39de3";
const WHITE = "#ffffff";

export function ChatBackdrop() {
  return (
    <Grainient
      className="grainient-backdrop"
      color1={PURPLE}
      color2={WHITE}
      color3={PURPLE}
      // Slow. This is peripheral vision next to text someone is reading, and
      // anything faster reads as a distraction rather than a surface.
      timeSpeed={1.4}
      colorBalance={-0.22}
      warpStrength={0.65}
      warpFrequency={5.0}
      warpSpeed={2.0}
      warpAmplitude={61}
      blendAngle={-9}
      blendSoftness={0.05}
      rotationAmount={500.0}
      noiseScale={2.0}
      grainAmount={0.05}
      grainScale={2.0}
      grainAnimated={false}
      contrast={1.5}
      gamma={1.0}
      saturation={0.95}
      centerX={0.0}
      centerY={0.0}
      zoom={0.9}
    />
  );
}
