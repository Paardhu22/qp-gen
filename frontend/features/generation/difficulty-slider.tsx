"use client";

import * as React from "react";

import { cn } from "@/lib/utils";
import {
  DEFAULT_LEVEL,
  describeLevel,
  explainLevel,
  mixPercents,
  normalizeLevel,
} from "./difficulty-profile";

/**
 * The paper's difficulty, as a slider rather than a switch.
 *
 * Moving it moves the *mix* of the paper — the share of basic, moderate and
 * challenging questions — a little at a time, and the bar beneath shows that mix
 * for the class being generated, so the teacher sees what a position means
 * before committing to it. Built on a native range input so the keyboard (arrow
 * keys, Home/End, Page Up/Down) and assistive technology work unchanged.
 */

const SEGMENTS = [
  { tier: "easy", label: "basic", dot: "bg-success" },
  { tier: "medium", label: "moderate", dot: "bg-warning" },
  { tier: "hard", label: "challenging", dot: "bg-destructive" },
] as const;

export function DifficultySlider({
  value,
  onChange,
  classNum,
  id = "difficulty-slider",
  label = "Difficulty",
  className,
}: {
  value: number;
  onChange: (level: number) => void;
  /** The class being generated: younger classes lean easier at the same position. */
  classNum?: number | string | null;
  id?: string;
  label?: string;
  className?: string;
}) {
  const level = normalizeLevel(value, DEFAULT_LEVEL);
  const mix = mixPercents(level, classNum);
  const summary = `${describeLevel(level)}: about ${mix.easy}% basic, ${mix.medium}% moderate and ${mix.hard}% challenging questions`;

  return (
    <div className={cn("w-full min-w-64 space-y-2", className)}>
      <div className="flex items-baseline justify-between gap-3">
        <label htmlFor={id} className="text-xs font-medium text-muted-foreground">
          {label}
        </label>
        <span className="text-sm font-semibold tabular-nums" aria-live="polite">
          {describeLevel(level)}
          <span className="ml-1.5 text-xs font-normal text-muted-foreground">{level}</span>
        </span>
      </div>

      <input
        id={id}
        type="range"
        min={0}
        max={100}
        step={5}
        value={level}
        onChange={(event) => onChange(Number(event.target.value))}
        aria-valuetext={summary}
        className="h-2 w-full cursor-pointer accent-primary"
      />

      <div className="grid grid-cols-3 text-[11px] text-muted-foreground" aria-hidden>
        <span className="text-left">Gentle</span>
        <span className="text-center">Balanced</span>
        <span className="text-right">Demanding</span>
      </div>

      <div
        className="flex h-2 w-full overflow-hidden rounded-full bg-muted"
        role="img"
        aria-label={summary}
      >
        {SEGMENTS.map(({ tier, dot }) => (
          <span
            key={tier}
            className={cn("h-full transition-[width] duration-200", dot)}
            style={{ width: `${mix[tier]}%` }}
          />
        ))}
      </div>

      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {SEGMENTS.map(({ tier, label: name, dot }) => (
          <li key={tier} className="flex items-center gap-1.5">
            <span className={cn("size-1.5 rounded-full", dot)} />
            <span className="tabular-nums">{mix[tier]}%</span> {name}
          </li>
        ))}
      </ul>

      <p className="text-xs text-muted-foreground">{explainLevel(level)}</p>
    </div>
  );
}
