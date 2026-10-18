"use client";

import * as React from "react";

import { cn } from "@/lib/utils";
import {
  DEFAULT_COLOURS,
  addEdit,
  clamp01,
  handlesOf,
  hitTest,
  isRect,
  moveEdit,
  rectFromDrag,
  removeEdit,
  resizeEdit,
  sanitizeEdits,
  type EditOp,
  type Handle,
  type ImageEdit,
  type RectEdit,
} from "./image-edits";

export type EditorTool = "select" | EditOp;

/** A touch of leeway, in pixels, for grabbing a handle. */
const HANDLE_GRAB_PX = 12;
const DRAW_TOOLS: readonly EditorTool[] = ["crop", "highlight", "box", "cover", "arrow"];

type Draft = { tool: EditorTool; x0: number; y0: number; x1: number; y1: number };
type Drag =
  | { kind: "move"; index: number; startX: number; startY: number; original: ImageEdit }
  | { kind: "handle"; index: number; handle: Handle };

/**
 * The picture with its edits drawn over it, and the tools to change them.
 *
 * It edits a list of instructions, not pixels: nothing here touches the image.
 * Pick a tool and drag on the picture to draw; pick Select to move, resize or
 * delete what is there. Everything works from the keyboard too: Tab to the
 * picture, then arrows to nudge the selected edit, Delete to remove it.
 */
export function ImageEditor({
  src,
  edits,
  onChange,
  tool,
  onToolChange,
  selected,
  onSelect,
  className,
}: {
  src: string;
  edits: ImageEdit[];
  onChange: (edits: ImageEdit[]) => void;
  tool: EditorTool;
  onToolChange: (tool: EditorTool) => void;
  selected: number;
  onSelect: (index: number) => void;
  className?: string;
}) {
  const boxRef = React.useRef<HTMLDivElement>(null);
  const [size, setSize] = React.useState({ w: 1, h: 1 });
  const [draft, setDraft] = React.useState<Draft | null>(null);
  const dragRef = React.useRef<Drag | null>(null);

  React.useLayoutEffect(() => {
    const el = boxRef.current;
    if (!el) return;
    const measure = () => setSize({ w: el.clientWidth || 1, h: el.clientHeight || 1 });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [src]);

  const toUnit = (event: React.PointerEvent | PointerEvent) => {
    const rect = boxRef.current!.getBoundingClientRect();
    return {
      x: clamp01((event.clientX - rect.left) / rect.width),
      y: clamp01((event.clientY - rect.top) / rect.height),
    };
  };

  const handleUnder = (edit: ImageEdit | undefined, x: number, y: number): Handle | null => {
    if (!edit) return null;
    for (const h of handlesOf(edit)) {
      if (Math.hypot((h.x - x) * size.w, (h.y - y) * size.h) <= HANDLE_GRAB_PX) return h.handle;
    }
    return null;
  };

  const onPointerDown = (event: React.PointerEvent) => {
    if (event.button !== 0) return;
    const { x, y } = toUnit(event);
    boxRef.current!.focus();
    (event.target as Element).setPointerCapture?.(event.pointerId);

    if (tool === "select") {
      const handle = handleUnder(edits[selected], x, y);
      if (handle) {
        dragRef.current = { kind: "handle", index: selected, handle };
        return;
      }
      const hit = hitTest(edits, x, y);
      onSelect(hit);
      if (hit >= 0) dragRef.current = { kind: "move", index: hit, startX: x, startY: y, original: edits[hit] };
      return;
    }

    if (tool === "label") {
      const next = addEdit(edits, { op: "label", x, y, text: "Label", color: DEFAULT_COLOURS.label });
      onChange(next);
      onSelect(next.length - 1);
      onToolChange("select");
      return;
    }

    if (DRAW_TOOLS.includes(tool)) setDraft({ tool, x0: x, y0: y, x1: x, y1: y });
  };

  const onPointerMove = (event: React.PointerEvent) => {
    const { x, y } = toUnit(event);
    if (draft) {
      setDraft({ ...draft, x1: x, y1: y });
      return;
    }
    const drag = dragRef.current;
    if (!drag) return;
    if (drag.kind === "move") {
      const moved = moveEdit(drag.original, x - drag.startX, y - drag.startY);
      onChange(edits.map((e, i) => (i === drag.index ? moved : e)));
    } else {
      onChange(edits.map((e, i) => (i === drag.index ? resizeEdit(e, drag.handle, x, y) : e)));
    }
  };

  const onPointerUp = () => {
    dragRef.current = null;
    if (!draft) return;
    const { tool: drawn, x0, y0, x1, y1 } = draft;
    setDraft(null);
    let edit: ImageEdit;
    if (drawn === "arrow") {
      edit = { op: "arrow", x1: x0, y1: y0, x2: x1, y2: y1, color: DEFAULT_COLOURS.arrow };
    } else {
      const r = rectFromDrag(x0, y0, x1, y1);
      edit = { op: drawn as RectEdit["op"], ...r, ...(drawn in DEFAULT_COLOURS ? { color: DEFAULT_COLOURS[drawn] } : {}) } as RectEdit;
    }
    // Validate before adding: a drag too small to be an edit (a stray click)
    // must not replace an existing crop.
    const [valid] = sanitizeEdits([edit]);
    if (!valid) return;
    const next = addEdit(edits, valid);
    onChange(next);
    onSelect(next.length - 1); // a new edit always goes on top
    onToolChange("select");
  };

  const onKeyDown = (event: React.KeyboardEvent) => {
    const edit = edits[selected];
    if (!edit) return;
    if (event.key === "Delete" || event.key === "Backspace") {
      event.preventDefault();
      onChange(removeEdit(edits, selected));
      onSelect(-1);
    } else if (event.key === "Escape") {
      onSelect(-1);
    } else if (event.key.startsWith("Arrow")) {
      event.preventDefault();
      const step = event.shiftKey ? 0.02 : 0.005;
      const dx = event.key === "ArrowRight" ? step : event.key === "ArrowLeft" ? -step : 0;
      const dy = event.key === "ArrowDown" ? step : event.key === "ArrowUp" ? -step : 0;
      onChange(edits.map((e, i) => (i === selected ? moveEdit(e, dx, dy) : e)));
    }
  };

  const px = (value: number, axis: "w" | "h") => value * size[axis];
  const draftRect = draft && draft.tool !== "arrow" ? rectFromDrag(draft.x0, draft.y0, draft.x1, draft.y1) : null;
  const unitPx = Math.min(size.w, size.h);

  return (
    <div
      ref={boxRef}
      tabIndex={0}
      role="application"
      aria-label="Image editor. Choose a tool, then drag on the picture. Use the arrow keys to nudge the selected edit and Delete to remove it."
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onKeyDown={onKeyDown}
      className={cn(
        "relative w-full select-none overflow-hidden rounded-md border bg-muted/30 outline-none focus-visible:ring-2 focus-visible:ring-ring",
        tool === "select" ? "cursor-default" : "cursor-crosshair",
        className,
      )}
      style={{ touchAction: "none" }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={src} alt="" draggable={false} className="block h-auto w-full" />

      {edits.map((edit, index) => {
        const active = index === selected;
        const ring = active ? "ring-2 ring-primary ring-offset-1" : "";
        if (isRect(edit)) {
          const style: React.CSSProperties = {
            left: `${edit.x * 100}%`,
            top: `${edit.y * 100}%`,
            width: `${edit.w * 100}%`,
            height: `${edit.h * 100}%`,
          };
          if (edit.op === "crop") {
            return (
              <div
                key={index}
                className={cn("pointer-events-none absolute border-2 border-dashed border-white", ring)}
                style={{ ...style, boxShadow: "0 0 0 9999px rgba(0,0,0,0.5)" }}
              />
            );
          }
          if (edit.op === "highlight") {
            return <div key={index} className={cn("pointer-events-none absolute", ring)} style={{ ...style, background: `${edit.color ?? "#ffd400"}61` }} />;
          }
          if (edit.op === "box") {
            return <div key={index} className={cn("pointer-events-none absolute border-2", ring)} style={{ ...style, borderColor: edit.color ?? "#e11d48" }} />;
          }
          return (
            <div key={index} className={cn("pointer-events-none absolute border border-dashed border-foreground/40 bg-white", ring)} style={style}>
              <span className="absolute inset-0 flex items-center justify-center text-[10px] text-muted-foreground">covered</span>
            </div>
          );
        }
        if (edit.op === "label") {
          return (
            <span
              key={index}
              className={cn("pointer-events-none absolute whitespace-nowrap font-semibold leading-none", ring)}
              style={{
                left: `${edit.x * 100}%`,
                top: `${edit.y * 100}%`,
                fontSize: Math.max(11, unitPx * 0.045),
                color: edit.color ?? "#111827",
                textShadow: "-1px -1px 0 #fff, 1px -1px 0 #fff, -1px 1px 0 #fff, 1px 1px 0 #fff",
              }}
            >
              {edit.text}
            </span>
          );
        }
        return null;
      })}

      {draftRect ? (
        <div
          className="pointer-events-none absolute border-2 border-dashed border-primary bg-primary/10"
          style={{ left: `${draftRect.x * 100}%`, top: `${draftRect.y * 100}%`, width: `${draftRect.w * 100}%`, height: `${draftRect.h * 100}%` }}
        />
      ) : null}

      <svg className="pointer-events-none absolute inset-0" width={size.w} height={size.h} aria-hidden>
        {[...edits.map((e, i) => ({ e, i })), ...(draft?.tool === "arrow" ? [{ e: { op: "arrow", x1: draft.x0, y1: draft.y0, x2: draft.x1, y2: draft.y1, color: "#2563eb" } as ImageEdit, i: -1 }] : [])].map(
          ({ e, i }) => {
            if (e.op !== "arrow") return null;
            const x1 = px(e.x1, "w");
            const y1 = px(e.y1, "h");
            const x2 = px(e.x2, "w");
            const y2 = px(e.y2, "h");
            const angle = Math.atan2(y2 - y1, x2 - x1);
            const head = Math.max(10, unitPx * 0.03);
            const colour = e.color ?? "#e11d48";
            const point = (a: number) => `${x2 - head * Math.cos(angle + a)},${y2 - head * Math.sin(angle + a)}`;
            return (
              <g key={i} stroke={colour} fill={colour}>
                <line x1={x1} y1={y1} x2={x2 - Math.cos(angle) * head * 0.6} y2={y2 - Math.sin(angle) * head * 0.6} strokeWidth={Math.max(2, unitPx * 0.006)} strokeLinecap="round" />
                <polygon points={`${x2},${y2} ${point(-Math.PI / 7)} ${point(Math.PI / 7)}`} stroke="none" />
                {i === selected ? <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#2563eb" strokeWidth={1} strokeDasharray="4 3" /> : null}
              </g>
            );
          },
        )}
      </svg>

      {tool === "select" && edits[selected]
        ? handlesOf(edits[selected]).map(({ handle, x, y }) => (
            <span
              key={handle}
              className="pointer-events-none absolute size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-sm border border-primary bg-background"
              style={{ left: `${x * 100}%`, top: `${y * 100}%` }}
            />
          ))
        : null}
    </div>
  );
}
