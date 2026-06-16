"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import GiftBow from "@/components/ui/GiftBow";

interface GiftOverlayProps {
  /** Called once the wrapping has fully opened and the page is revealed. */
  onOpened?: () => void;
}

const SESSION_KEY = "hsat_gift_opened";

// Wrapping-paper panels (slightly lighter than the ribbon so the bands pop).
const WRAP_TOP = "linear-gradient(180deg, #fdf8ff 0%, #f1e6ff 58%, #e4d3fb 100%)";
const WRAP_BOTTOM = "linear-gradient(0deg, #fdf8ff 0%, #f1e6ff 58%, #e4d3fb 100%)";
const PAPER_PATTERN =
  "repeating-linear-gradient(45deg, rgba(255,255,255,0.16) 0px, rgba(255,255,255,0.16) 18px, transparent 18px, transparent 38px)";
const VIGNETTE =
  "radial-gradient(125% 120% at 50% 50%, transparent 52%, rgba(92,48,160,0.14) 100%)";

// Vermilion-burnt-orange satin ribbon: deep mahogany shadow edges -> rich
// vermilion body -> burnt orange highlight -> restrained warm peach sheen,
// giving glossy silk depth without neon orange or flat red.
const BAND_H =
  "linear-gradient(180deg, #3A0E00 0%, #6B1A00 7%, #8F2E00 19%, #B34000 32%, #C85A10 41%, #DC7030 46%, #F09060 49.5%, #D06030 53%, #B34000 63%, #8F2E00 79%, #6B1A00 92%, #3A0E00 100%)";
const BAND_V =
  "linear-gradient(90deg, #3A0E00 0%, #6B1A00 7%, #8F2E00 19%, #B34000 32%, #C85A10 41%, #DC7030 46%, #F09060 49.5%, #D06030 53%, #B34000 63%, #8F2E00 79%, #6B1A00 92%, #3A0E00 100%)";
const BAND_SHADOW_H =
  "0 18px 36px rgba(58,14,0,0.34), 0 -10px 26px rgba(58,14,0,0.18)";
const BAND_SHADOW_V = "0 0 36px rgba(58,14,0,0.32)";
const GLOW =
  "radial-gradient(circle, rgba(180,60,10,0.34) 0%, rgba(180,60,10,0) 66%)";

// Responsive sizing — the present should fill the screen and the bow dominates.
const BAND_THICKNESS = "clamp(72px, 13vmin, 132px)";
const BOW_WIDTH = "clamp(280px, 54vmin, 560px)";

// Satisfying ease for the wrapping parting open.
const OPEN_EASE: [number, number, number, number] = [0.83, 0, 0.17, 1];

const CONFETTI_COLORS = [
  "#C85A10", // burnt orange
  "#B34000", // vermilion
  "#DC7030", // warm red-orange
  "#F5B8A0", // warm peach
  "#E8C36B", // gold
  "#FFF1E6", // cream
];

export default function GiftOverlay({ onOpened }: GiftOverlayProps) {
  const reduce = !!useReducedMotion();

  const [opened, setOpened] = useState(false); // wrapping gone, page revealed
  const [cutting, setCutting] = useState(false); // bow tapped -> untie + hide hint
  const [opening, setOpening] = useState(false); // wrapping parts + confetti
  const [confettiOn, setConfettiOn] = useState(false);

  const onOpenedRef = useRef(onOpened);
  const startedRef = useRef(false);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    onOpenedRef.current = onOpened;
  }, [onOpened]);

  // Greet each visitor with the wrapping only once per session.
  useEffect(() => {
    try {
      if (sessionStorage.getItem(SESSION_KEY) === "1") setOpened(true);
    } catch {
      /* sessionStorage may be unavailable; just show the intro */
    }
    const timers = timersRef.current;
    return () => timers.forEach(clearTimeout);
  }, []);

  // Lock background scroll while the wrapping still covers the page.
  useEffect(() => {
    if (opened) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [opened]);

  const startOpening = useCallback(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    setOpening(true);
    if (!reduce) {
      setConfettiOn(true);
      timersRef.current.push(setTimeout(() => setConfettiOn(false), 2000));
    }
  }, [reduce]);

  const handleTap = useCallback(() => {
    if (cutting) return;
    setCutting(true); // bow begins to untie, hint disappears
    // Let the bow loosen for a beat, then snap the wrapping open.
    timersRef.current.push(setTimeout(startOpening, 380));
    // Safety net in case a timer is dropped: reveal anyway.
    timersRef.current.push(setTimeout(startOpening, 3500));
  }, [cutting, startOpening]);

  const finishReveal = useCallback(() => {
    setOpened(true);
    try {
      sessionStorage.setItem(SESSION_KEY, "1");
    } catch {
      /* ignore */
    }
    onOpenedRef.current?.();
  }, []);

  const confettiPieces = useMemo(
    () =>
      Array.from({ length: 26 }, (_, i) => {
        const dist = 150 + Math.random() * 260;
        return {
          id: i,
          x: (Math.random() - 0.5) * 2 * dist,
          up: 110 + Math.random() * 190,
          fall: 320 + Math.random() * 380,
          rotate: (Math.random() - 0.5) * 760,
          size: 9 + Math.random() * 9,
          color: CONFETTI_COLORS[i % CONFETTI_COLORS.length],
          delay: Math.random() * 0.14,
          duration: 1.2 + Math.random() * 0.7,
          round: Math.random() > 0.6,
        };
      }),
    [],
  );

  const bandTransition = { duration: reduce ? 0 : 0.95, ease: OPEN_EASE };

  return (
    <>
      {!opened && (
        <div
          className="fixed inset-0 z-50 overflow-hidden"
          role="dialog"
          aria-modal="true"
          aria-label="Unwrap the page"
        >
          {/* ---- Wrapping paper: two halves that part to reveal the page ---- */}
          <motion.div
            aria-hidden="true"
            className="absolute inset-x-0 top-0 h-1/2 overflow-hidden"
            style={{ background: WRAP_TOP }}
            initial={false}
            animate={{ y: opening ? "-100%" : "0%" }}
            transition={bandTransition}
          >
            <div className="absolute inset-0" style={{ background: PAPER_PATTERN }} />
            <div className="absolute inset-0" style={{ background: VIGNETTE }} />
          </motion.div>
          <motion.div
            aria-hidden="true"
            className="absolute inset-x-0 bottom-0 h-1/2 overflow-hidden"
            style={{ background: WRAP_BOTTOM }}
            initial={false}
            animate={{ y: opening ? "100%" : "0%" }}
            transition={bandTransition}
            onAnimationComplete={() => {
              if (opening) finishReveal();
            }}
          >
            <div className="absolute inset-0" style={{ background: PAPER_PATTERN }} />
            <div className="absolute inset-0" style={{ background: VIGNETTE }} />
          </motion.div>

          {/* ---- Vertical ribbon band (full height), splits up/down ----
               Centering (x: -50%) lives in framer's transform, since framer
               owns `transform` and would otherwise clobber a Tailwind class. */}
          <motion.div
            aria-hidden="true"
            className="absolute top-0 left-1/2 h-1/2"
            style={{ width: BAND_THICKNESS, background: BAND_V, boxShadow: BAND_SHADOW_V }}
            initial={false}
            animate={{ x: "-50%", y: opening ? "-100%" : "0%" }}
            transition={bandTransition}
          />
          <motion.div
            aria-hidden="true"
            className="absolute bottom-0 left-1/2 h-1/2"
            style={{ width: BAND_THICKNESS, background: BAND_V, boxShadow: BAND_SHADOW_V }}
            initial={false}
            animate={{ x: "-50%", y: opening ? "100%" : "0%" }}
            transition={bandTransition}
          />

          {/* ---- Horizontal ribbon band (full width), splits left/right, on top ---- */}
          <motion.div
            aria-hidden="true"
            className="absolute left-0 top-1/2 w-1/2"
            style={{ height: BAND_THICKNESS, background: BAND_H, boxShadow: BAND_SHADOW_H }}
            initial={false}
            animate={{ y: "-50%", x: opening ? "-100%" : "0%" }}
            transition={bandTransition}
          />
          <motion.div
            aria-hidden="true"
            className="absolute right-0 top-1/2 w-1/2"
            style={{ height: BAND_THICKNESS, background: BAND_H, boxShadow: BAND_SHADOW_H }}
            initial={false}
            animate={{ y: "-50%", x: opening ? "100%" : "0%" }}
            transition={bandTransition}
          />

          {/* ---- Center stage: title, the bow (focal CTA), instruction ---- */}
          <motion.div
            className="absolute inset-0 z-10 grid place-items-center px-6"
            style={{ pointerEvents: "none" }}
            animate={{ opacity: opening ? 0 : 1 }}
            transition={{ duration: reduce ? 0 : 0.45, ease: "easeInOut" }}
          >
            <div className="relative grid place-items-center">
              {/* Soft glow behind the bow */}
              <motion.div
                aria-hidden="true"
                className="pointer-events-none absolute left-1/2 top-1/2 rounded-full"
                style={{
                  width: "clamp(320px, 64vmin, 760px)",
                  height: "clamp(320px, 64vmin, 760px)",
                  background: GLOW,
                }}
                initial={{ x: "-50%", y: "-50%", opacity: 0.4, scale: 0.94 }}
                animate={
                  cutting
                    ? { x: "-50%", y: "-50%", opacity: 0, scale: 1.4 }
                    : reduce
                      ? { x: "-50%", y: "-50%", opacity: 0.55, scale: 1 }
                      : {
                          x: "-50%",
                          y: "-50%",
                          opacity: [0.4, 0.7, 0.4],
                          scale: [0.94, 1.06, 0.94],
                        }
                }
                transition={
                  cutting
                    ? { duration: 0.5 }
                    : { duration: 3.6, repeat: reduce ? 0 : Infinity, ease: "easeInOut" }
                }
              />

              {/* The bow itself — the primary call to action.
                  Centered by the grid (no transform), so framer is free to own
                  the idle bounce / hover scale / untie transforms. */}
              <motion.button
                type="button"
                onClick={handleTap}
                aria-label="Open your gift"
                className="relative block border-0 bg-transparent p-0"
                style={{
                  pointerEvents: "auto",
                  cursor: cutting ? "default" : "pointer",
                  transformOrigin: "center",
                  WebkitTapHighlightColor: "transparent",
                }}
                animate={
                  cutting
                    ? { scale: 1.32, opacity: 0, y: -18, rotate: 5 }
                    : reduce
                      ? { y: 0, rotate: 0, scale: 1 }
                      : { y: [0, -12, 0], rotate: [-1.6, 1.6, -1.6], scale: 1 }
                }
                transition={
                  cutting
                    ? { duration: 0.5, ease: "easeIn" }
                    : { duration: 3.4, repeat: reduce ? 0 : Infinity, ease: "easeInOut" }
                }
                whileHover={cutting ? undefined : { scale: 1.07 }}
                whileTap={cutting ? undefined : { scale: 0.95 }}
              >
                <GiftBow
                  style={{
                    width: BOW_WIDTH,
                    height: "auto",
                    display: "block",
                    filter: "drop-shadow(0 22px 34px rgba(58,14,0,0.52))",
                  }}
                />
              </motion.button>

              {/* Instruction — readable, noticeable pill that points at the bow.
                  Outer div handles positioning/centering (plain CSS); the inner
                  motion element only animates opacity/y, so no transform clash. */}
              <div className="absolute top-full left-1/2 mt-6 -translate-x-1/2 sm:mt-9">
                <AnimatePresence>
                  {!cutting && (
                    <motion.div
                      key="hint"
                      initial={{ opacity: 0, y: 12 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -6 }}
                      transition={{ duration: 0.4 }}
                      className="flex items-center gap-2 whitespace-nowrap rounded-full px-5 py-2.5 font-medium backdrop-blur-sm"
                      style={{
                        fontSize: "clamp(1rem, 2.6vmin, 1.35rem)",
                        color: "#7A2A00",
                        background: "rgba(255,250,248,0.74)",
                        boxShadow: "0 10px 26px rgba(58,14,0,0.18)",
                      }}
                    >
                      <motion.svg
                        width="18"
                        height="18"
                        viewBox="0 0 24 24"
                        fill="none"
                        aria-hidden="true"
                        animate={reduce ? { y: 0 } : { y: [0, -5, 0] }}
                        transition={{
                          duration: 1.4,
                          repeat: reduce ? 0 : Infinity,
                          ease: "easeInOut",
                        }}
                      >
                        <path
                          d="M5 15l7-7 7 7"
                          stroke="currentColor"
                          strokeWidth="2.5"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </motion.svg>
                      Click the bow to unwrap
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </div>
          </motion.div>
        </div>
      )}

      {/* Confetti lives above everything and outlives the wrapping, so it spills
          briefly over the freshly revealed page. */}
      {confettiOn && (
        <div
          className="pointer-events-none fixed inset-0 z-[60] overflow-hidden"
          aria-hidden="true"
        >
          {confettiPieces.map((p) => (
            <motion.span
              key={p.id}
              initial={{ x: 0, y: 0, opacity: 0, rotate: 0 }}
              animate={{
                x: [0, p.x * 0.5, p.x],
                y: [0, -p.up, p.fall],
                opacity: [0, 1, 1, 0],
                rotate: [0, p.rotate],
              }}
              transition={{ duration: p.duration, delay: p.delay, ease: "easeOut" }}
              style={{
                position: "absolute",
                left: "50%",
                top: "50%",
                width: p.size,
                height: p.round ? p.size : p.size * 0.5,
                borderRadius: p.round ? "9999px" : 2,
                background: p.color,
                boxShadow: "0 1px 2px rgba(80,50,140,0.18)",
              }}
            />
          ))}
        </div>
      )}
    </>
  );
}
