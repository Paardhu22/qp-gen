"use client";

/**
 * A question paper coming off the press.
 *
 * Generation takes three to four minutes and the stream goes genuinely silent
 * for long stretches of it — a Model 1 batch emits nothing until the whole
 * batch lands, and Model 2's assembly is a single non-streaming call. A
 * spinner over that reads as a hang.
 *
 * So this reports rather than entertains. Every stage below is a real stage
 * (`services/pool/pipeline.py` emits them as `status`, `plan`, `pool`,
 * `question` and `set` events) and every number is a real count. The control
 * strip inks up one swatch per stage; the sheet fills with the teacher's
 * actual questions as they arrive. The only invented motion is the raking
 * light across the sheet, which is ambient and the first thing dropped under
 * `prefers-reduced-motion`.
 */

import * as React from "react";

import { cn } from "@/lib/utils";

export type PressStageId =
  | "reading_chapters"
  | "plan"
  | "generating_pool"
  | "assembling"
  | "printing"
  | "sets";

const STAGES: { id: PressStageId; name: string; short: string }[] = [
  { id: "reading_chapters", name: "Reading chapters", short: "Read" },
  { id: "plan", name: "Compiling blueprint", short: "Plate" },
  { id: "generating_pool", name: "Writing questions", short: "Ink" },
  { id: "assembling", name: "Selecting for paper", short: "Impose" },
  { id: "printing", name: "Setting the paper", short: "Print" },
  { id: "sets", name: "Deriving sets", short: "Sets" },
];

export interface PressRow {
  /** Section heading this question sits under, if it opens one. */
  section?: string;
  number: number;
  marks: number;
  text: string;
}

export interface PressCheckProps {
  /** The furthest stage reached. Everything before it renders as done. */
  stage: PressStageId;
  /** Free-text line from the pipeline's own `status` events. */
  status: string;
  /** Questions that have actually arrived, in order. */
  rows: PressRow[];
  /** How many slots the blueprint declared, once it exists. */
  plannedSlots?: number;
  /** Pool size, once Model 1 is done. */
  poolCount?: number;
  /** Derived set labels that have landed ("B", "C"). */
  sets?: string[];
  /** Paper identity for the masthead. */
  subject?: string;
  academicClass?: string;
  marks?: string;
  done?: boolean;
}

function useElapsed(active: boolean) {
  const [seconds, setSeconds] = React.useState(0);
  React.useEffect(() => {
    if (!active) return;
    const started = Date.now();
    const id = window.setInterval(
      () => setSeconds(Math.floor((Date.now() - started) / 1000)),
      1000,
    );
    return () => window.clearInterval(id);
  }, [active]);
  return seconds;
}

export function PressCheck({
  stage,
  status,
  rows,
  plannedSlots,
  poolCount,
  sets = [],
  subject = "Science",
  academicClass = "X",
  marks = "80",
  done = false,
}: PressCheckProps) {
  const elapsed = useElapsed(!done);
  const feedRef = React.useRef<HTMLDivElement>(null);
  const sheetRef = React.useRef<HTMLElement>(null);
  const [feedOffset, setFeedOffset] = React.useState(0);

  const stageIndex = STAGES.findIndex((s) => s.id === stage);

  // Feed the sheet upward once the page is full, so the paper visibly grows
  // instead of silently overflowing its own edge.
  React.useEffect(() => {
    const feed = feedRef.current;
    const sheet = sheetRef.current;
    if (!feed || !sheet) return;
    const overflow = feed.scrollHeight - sheet.clientHeight;
    setFeedOffset(overflow > 0 ? overflow : 0);
  }, [rows.length]);

  const stateOf = (index: number) =>
    done || index < stageIndex ? "done" : index === stageIndex ? "active" : "waiting";

  const countFor = (id: PressStageId): string => {
    if (id === "plan") return plannedSlots ? `${plannedSlots} slots` : "";
    if (id === "generating_pool") return poolCount ? `${poolCount}` : "";
    if (id === "printing" && plannedSlots) return `${rows.length}/${plannedSlots}`;
    if (id === "printing") return rows.length ? `${rows.length}` : "";
    if (id === "sets" && sets.length) return sets.join(" · ");
    return "";
  };

  return (
    <div className="press-check grid gap-8 lg:grid-cols-[220px_minmax(0,1fr)]">
      {/* Job ticket */}
      <aside className="flex flex-col gap-5">
        <div className="flex flex-col gap-1.5 border-b border-[var(--pc-hairline)] pb-4">
          <span className="text-[10.5px] uppercase tracking-[0.18em] text-[var(--pc-chrome)]">
            Job ticket
          </span>
          <span className="text-lg tabular-nums text-[var(--pc-reg-lift)]">
            {subject} · Class {academicClass}
          </span>
          <span className="text-xs leading-relaxed text-[var(--pc-chrome-dim)]">
            {marks} marks · {sets.length + 1} set{sets.length ? "s" : ""}
          </span>
        </div>

        <ol className="flex list-none flex-col gap-0.5 p-0">
          {STAGES.map((s, index) => {
            const state = stateOf(index);
            return (
              <li
                key={s.id}
                className={cn(
                  "grid grid-cols-[16px_minmax(0,1fr)_auto] items-baseline gap-2.5 py-1.5 transition-colors",
                  state === "active"
                    ? "text-[var(--pc-reg-lift)]"
                    : state === "done"
                      ? "text-[var(--pc-chrome)]"
                      : "text-[var(--pc-chrome-dim)]",
                )}
              >
                <span
                  className={cn(
                    "mt-1 h-[7px] w-[7px] self-start justify-self-center rounded-full border border-current",
                    state !== "waiting" && "bg-current",
                    state === "active" && "pc-pulse",
                  )}
                />
                <span className="text-[12.5px]">{s.name}</span>
                <span className="text-[11.5px] tabular-nums">
                  {countFor(s.id)}
                </span>
              </li>
            );
          })}
        </ol>

        <div className="flex items-baseline justify-between border-t border-[var(--pc-hairline)] pt-4 tabular-nums">
          <span className="text-[10.5px] uppercase tracking-[0.16em] text-[var(--pc-chrome-dim)]">
            Elapsed
          </span>
          <span className="text-[15px] text-[var(--pc-chrome)]">
            {Math.floor(elapsed / 60)}:
            {String(elapsed % 60).padStart(2, "0")}
          </span>
        </div>
      </aside>

      {/* Plate */}
      <div className="flex min-w-0 flex-col gap-6">
        <div className="relative flex justify-center p-6">
          <span className="pc-crop absolute left-0 top-0 border-l border-t" />
          <span className="pc-crop absolute right-0 top-0 border-r border-t" />
          <span className="pc-crop absolute bottom-0 left-0 border-b border-l" />
          <span className="pc-crop absolute bottom-0 right-0 border-b border-r" />

          <svg
            className="pointer-events-none absolute right-8 top-0.5 h-[18px] w-[18px]"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <circle cx="12" cy="12" r="7" fill="none" stroke="var(--pc-chrome-dim)" strokeWidth="1" />
            <circle cx="12" cy="12" r="2.5" fill="none" stroke="var(--pc-mark)" strokeWidth="1" />
            <path d="M12 1v7M12 16v7M1 12h7M16 12h7" stroke="var(--pc-chrome-dim)" strokeWidth="1" />
          </svg>

          <div className="relative w-full max-w-[460px]">
            {sets.includes("C") && <span className="pc-ghost pc-ghost-c" />}
            {sets.includes("B") && <span className="pc-ghost pc-ghost-b" />}

            <article
              ref={sheetRef}
              className="pc-sheet"
              aria-label="Question paper being generated"
            >
              <div
                ref={feedRef}
                className="pc-feed"
                style={{ transform: `translateY(${-feedOffset}px)` }}
              >
                <header className="pc-masthead">
                  <div className="pc-masthead-rule" />
                  <div className="pc-masthead-title">Question Paper</div>
                  <div className="pc-masthead-line">
                    {subject} — Class {academicClass}
                  </div>
                  <div className="pc-masthead-meta">
                    <span>Time: 3 Hours</span>
                    <span>Maximum Marks: {marks}</span>
                  </div>
                </header>

                {/* The blueprint's empty slots, drawn before any text exists.
                    Seeing the shape of the paper first is what makes a silent
                    three-minute stretch legible. */}
                {plannedSlots
                  ? Array.from({ length: plannedSlots }).map((_, index) => {
                      const row = rows[index];
                      if (!row) return <div key={index} className="pc-slot" />;
                      return (
                        <React.Fragment key={index}>
                          {row.section && (
                            <div className="pc-section">
                              <span>{row.section}</span>
                            </div>
                          )}
                          <div className="pc-qrow">
                            <span className="pc-qno">{row.number}.</span>
                            <span className="pc-qbody">{row.text}</span>
                            <span className="pc-qmarks">[{row.marks}]</span>
                          </div>
                        </React.Fragment>
                      );
                    })
                  : null}
              </div>
            </article>
          </div>
        </div>

        {/* Control strip */}
        <div className="flex flex-col gap-2.5">
          <div className="grid grid-cols-6 gap-[3px]">
            {STAGES.map((s, index) => (
              <span
                key={s.id}
                className="pc-swatch"
                data-inked={
                  stateOf(index) === "done"
                    ? "full"
                    : stateOf(index) === "active"
                      ? "partial"
                      : "none"
                }
              />
            ))}
          </div>
          <div className="grid grid-cols-6 gap-[3px] text-[9.5px] uppercase tracking-[0.1em]">
            {STAGES.map((s, index) => (
              <span
                key={s.id}
                className={cn(
                  "truncate",
                  stateOf(index) === "waiting"
                    ? "text-[var(--pc-chrome-dim)]"
                    : "text-[var(--pc-chrome)]",
                )}
              >
                {s.short}
              </span>
            ))}
          </div>

          <div className="flex items-baseline justify-between gap-4 pt-1">
            <span className="text-[13px] text-[var(--pc-reg-lift)]">
              {/* Coerced, not trusted: `status` is fed straight from SSE
                  payloads. A non-string here (the `plan` event's `summary` is
                  an object, for one) would otherwise throw "Objects are not
                  valid as a React child" and take the whole page down mid
                  generation, losing the stream. */}
              {done
                ? "Paper ready"
                : (typeof status === "string" ? status : "") ||
                  "Starting the press…"}
            </span>
            <span className="text-[11.5px] text-[var(--pc-chrome-dim)]">
              {done
                ? "opening in the editor"
                : poolCount
                  ? `pool of ${poolCount}`
                  : ""}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
