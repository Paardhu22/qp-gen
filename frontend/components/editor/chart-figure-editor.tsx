"use client";

/**
 * The data a chart will be drawn from, laid out for correction.
 *
 * This panel is the reason the figure flow has two steps. The renderer behind
 * it is exact — a wedge is the angle its value says, a bar lands on its
 * gridline — but exactness is worth nothing if the numbers came out of the
 * question wrong, and the only person who can see that is the teacher who
 * wrote it. So the numbers are shown, and they are editable.
 *
 * Redrawing costs nothing (no model call, no spend — arithmetic on the
 * server), which is what makes a live preview affordable at all. It is
 * debounced only so a four-digit value does not fire four renders.
 */

import * as React from "react";

import { renderQuestionFigure, type ChartSpec } from "@/lib/api-client";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";

/** Long enough to swallow typing, short enough that the chart feels live. */
const REDRAW_DELAY_MS = 400;

const CHART_LABELS: Record<ChartSpec["chart"], string> = {
  pie: "Pie chart",
  bar: "Bar graph",
  histogram: "Histogram",
  line: "Line graph",
  number_line: "Number line",
  coordinate_grid: "Coordinate grid",
};

interface Props {
  spec: ChartSpec;
  onSpecChange: (spec: ChartSpec) => void;
  /** The URL of the drawn chart, once one exists. Lifted so the parent can
   *  insert it without redrawing. */
  onPreviewChange: (url: string | null) => void;
}

export function ChartFigureEditor({ spec, onSpecChange, onPreviewChange }: Props) {
  const [previewUrl, setPreviewUrl] = React.useState<string | null>(null);
  const [drawing, setDrawing] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  // Redraw whenever the spec settles. The request is keyed by a serialization
  // of the spec rather than the object, so a re-render that produces an equal
  // spec does not refetch.
  const key = JSON.stringify(spec);
  React.useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      setDrawing(true);
      setError(null);
      try {
        const { imageUrl } = await renderQuestionFigure({ spec: JSON.parse(key) });
        if (cancelled) return;
        setPreviewUrl(imageUrl);
        onPreviewChange(imageUrl);
      } catch (err: any) {
        if (cancelled) return;
        // A spec the teacher has broken mid-edit (an emptied value) is the
        // common case here, so the old drawing stays on screen rather than
        // flashing away between keystrokes.
        setError(err?.message || "Those values cannot be drawn.");
        onPreviewChange(null);
      } finally {
        if (!cancelled) setDrawing(false);
      }
    }, REDRAW_DELAY_MS);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [key]);

  const patch = (changes: Partial<ChartSpec>) => onSpecChange({ ...spec, ...changes });

  return (
    <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_190px]">
      <div className="flex min-w-0 flex-col gap-3">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          {CHART_LABELS[spec.chart]} — read from your question
        </p>

        <div className="flex max-h-56 flex-col gap-1.5 overflow-y-auto pr-1">
          {spec.series?.map((datum, index) => (
            <div key={index} className="grid grid-cols-[minmax(0,1fr)_84px] gap-2">
              <Input
                value={datum.label}
                aria-label={`Label ${index + 1}`}
                className="h-8 text-xs"
                onChange={(event) => {
                  const series = [...(spec.series ?? [])];
                  series[index] = { ...datum, label: event.target.value };
                  patch({ series });
                }}
              />
              <Input
                value={String(datum.value)}
                inputMode="decimal"
                aria-label={`Value for ${datum.label}`}
                className="h-8 text-right text-xs tabular-nums"
                onChange={(event) => {
                  const series = [...(spec.series ?? [])];
                  series[index] = { ...datum, value: Number(event.target.value) };
                  patch({ series });
                }}
              />
            </div>
          ))}

          {spec.bins?.map((bin, index) => (
            <div key={index} className="grid grid-cols-[1fr_1fr_84px] gap-2">
              {(["lower", "upper", "value"] as const).map((field) => (
                <Input
                  key={field}
                  value={String(bin[field])}
                  inputMode="decimal"
                  aria-label={`${field} of class ${index + 1}`}
                  className="h-8 text-right text-xs tabular-nums"
                  onChange={(event) => {
                    const bins = [...(spec.bins ?? [])];
                    bins[index] = { ...bin, [field]: Number(event.target.value) };
                    patch({ bins });
                  }}
                />
              ))}
            </div>
          ))}

          {spec.points?.map((point, index) => (
            <div key={index} className="grid grid-cols-[1fr_64px_64px] gap-2">
              <Input
                value={point.label}
                aria-label={`Point ${index + 1} label`}
                className="h-8 text-xs"
                onChange={(event) => {
                  const points = [...(spec.points ?? [])];
                  points[index] = { ...point, label: event.target.value };
                  patch({ points });
                }}
              />
              {(["x", "y"] as const).map((axis) => (
                <Input
                  key={axis}
                  value={String(point[axis])}
                  inputMode="decimal"
                  aria-label={`${axis} of point ${index + 1}`}
                  className="h-8 text-right text-xs tabular-nums"
                  onChange={(event) => {
                    const points = [...(spec.points ?? [])];
                    points[index] = { ...point, [axis]: Number(event.target.value) };
                    patch({ points });
                  }}
                />
              ))}
            </div>
          ))}
        </div>

        <div className="grid grid-cols-2 gap-2">
          <Input
            value={spec.xLabel}
            placeholder="Horizontal axis"
            aria-label="Horizontal axis label"
            className="h-8 text-xs"
            onChange={(event) => patch({ xLabel: event.target.value })}
          />
          <Input
            value={spec.yLabel}
            placeholder="Vertical axis"
            aria-label="Vertical axis label"
            className="h-8 text-xs"
            onChange={(event) => patch({ yLabel: event.target.value })}
          />
        </div>

        {/* The one control that changes what the question asks, so it says so
            rather than being labelled "show values". */}
        <label className="flex items-start gap-2 text-xs text-muted-foreground">
          <input
            type="checkbox"
            checked={spec.showValues}
            className="mt-0.5 size-3.5 accent-primary"
            onChange={(event) => patch({ showValues: event.target.checked })}
          />
          <span>
            Print the numbers on the figure.{" "}
            <span className="text-muted-foreground/70">
              Leave this off if the student is meant to read them off the chart.
            </span>
          </span>
        </label>
      </div>

      <div className="flex flex-col gap-1.5">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          Preview
        </p>
        <div
          className={cn(
            "relative flex min-h-[150px] items-center justify-center rounded-lg border border-border bg-white p-2",
            error && "border-destructive/50",
          )}
        >
          {previewUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={previewUrl}
              alt=""
              className={cn(
                "max-h-44 w-full object-contain transition-opacity",
                drawing && "opacity-50",
              )}
            />
          ) : (
            <Spinner className="size-4" />
          )}
        </div>
        {error ? (
          <p className="text-[11px] leading-snug text-destructive">{error}</p>
        ) : null}
      </div>
    </div>
  );
}
