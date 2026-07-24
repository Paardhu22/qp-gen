"use client";

/**
 * Comparison Workspace — the primary interface for reviewing a multi-set
 * generation (Sets A / B / C produced in one SSE run).
 *
 * It replaces the old single-set "switcher" for multi-set output. Two or three
 * sets are shown side by side, aligned row-for-row by the blueprint slot index
 * so sections and marks line up horizontally and one scrollbar keeps every
 * column in sync (structural synchronised scrolling — no manual scroll
 * mirroring needed). Questions that are identical across the shown sets are
 * marked "same"; questions that differ are highlighted "changed".
 *
 * Insertion is set-scoped: Insert Single / Insert Section / Insert Set for each
 * of A, B, C, routed through the store's `appendSections` with a `setLabel` so
 * the TipTap editor renders "Set B · Section A" headers and the sets never
 * collide in one document (the regression this view fixes).
 *
 * v1 is read + diff + insert. Inline edit, per-question regenerate, and
 * move-between-sets are deferred.
 */
import { useMemo, useState } from "react";
import {
  useEditorStore,
  type ComparisonSet,
  type Question,
  type SectionToAppend,
} from "@/store/editor-store";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { CheckCircle2, Columns3, Plus, X } from "lucide-react";

// ── Row model: one aligned blueprint slot across the shown sets ──────────────
interface SlotRow {
  slotIndex: number;
  sectionTitle: string;
  /** question per set label; missing if a set didn't fill this slot */
  byLabel: Record<string, any>;
  /** true when every shown set has this slot AND the content matches */
  identical: boolean;
}

interface SectionGroup {
  title: string;
  rows: SlotRow[];
}

const norm = (s: unknown) =>
  String(s ?? "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();

/** Map a set's assembled-paper result into editor Question shape. */
function toEditorQuestion(q: any): Question {
  return {
    content: q.content,
    type: q.type,
    options: q.options || [],
    answer: q.answer,
    marks: q.marks,
    image_url: q.image_url || q.metadata?.image_url || "",
  };
}

/** Stable slot key: prefer the blueprint slotIndex, fall back to position. */
function slotKeyOf(q: any, fallback: number): number {
  const raw = Number(q?.metadata?.slotIndex);
  return Number.isFinite(raw) ? raw : fallback;
}

/**
 * Build the aligned section→row model for the chosen sets. Sections are ordered
 * by first appearance in the first shown set (blueprint order); rows within a
 * section are ordered by slotIndex.
 */
function buildGroups(
  sets: ComparisonSet[],
  shown: string[],
): SectionGroup[] {
  const shownSets = sets.filter((s) => shown.includes(s.label));
  // slotIndex -> { sectionTitle, byLabel }
  const slots = new Map<
    number,
    { sectionTitle: string; order: number; byLabel: Record<string, any> }
  >();
  // Preserve section order from the first shown set.
  const sectionOrder: string[] = [];
  let globalOrder = 0;

  shownSets.forEach((set) => {
    let posFallback = 0;
    (set.result?.sections || []).forEach((section: any) => {
      const title = String(section.title || "Questions");
      if (!sectionOrder.includes(title)) sectionOrder.push(title);
      (section.questions || []).forEach((q: any) => {
        const key = slotKeyOf(q, posFallback++);
        const entry = slots.get(key) || {
          sectionTitle: title,
          order: globalOrder++,
          byLabel: {} as Record<string, any>,
        };
        entry.byLabel[set.label] = q;
        // Prefer a real section title if this is the first time we see the slot.
        if (!entry.sectionTitle) entry.sectionTitle = title;
        slots.set(key, entry);
      });
    });
  });

  const rows: SlotRow[] = Array.from(slots.entries())
    .map(([slotIndex, e]) => {
      const present = shown
        .map((l) => e.byLabel[l])
        .filter((q) => q != null);
      const contents = present.map((q) => norm(q.content));
      const identical =
        present.length === shown.length &&
        contents.every((c) => c === contents[0]);
      return {
        slotIndex,
        sectionTitle: e.sectionTitle,
        byLabel: e.byLabel,
        identical,
        _order: e.order,
      } as SlotRow & { _order: number };
    })
    .sort(
      (a: any, b: any) =>
        a.slotIndex - b.slotIndex || a._order - b._order,
    );

  // Group by section, preserving section order.
  const byTitle = new Map<string, SlotRow[]>();
  for (const r of rows) {
    const list = byTitle.get(r.sectionTitle) || [];
    list.push(r);
    byTitle.set(r.sectionTitle, list);
  }
  return sectionOrder
    .filter((t) => byTitle.has(t))
    .map((title) => ({ title, rows: byTitle.get(title)! }));
}

export function ComparisonWorkspace() {
  const sets = useEditorStore((s) => s.comparisonSets);
  const open = useEditorStore((s) => s.comparisonOpen);
  const setOpen = useEditorStore((s) => s.setComparisonOpen);
  const appendSections = useEditorStore((s) => s.appendSections);

  const availableLabels = useMemo(() => sets.map((s) => s.label), [sets]);
  const [shown, setShown] = useState<string[]>(availableLabels);

  // Keep `shown` valid if the available sets change between generations.
  const effectiveShown = useMemo(() => {
    const valid = shown.filter((l) => availableLabels.includes(l));
    return valid.length >= 2
      ? valid
      : availableLabels.slice(0, Math.max(2, availableLabels.length));
  }, [shown, availableLabels]);

  const groups = useMemo(
    () => buildGroups(sets, effectiveShown),
    [sets, effectiveShown],
  );

  if (!open || sets.length < 2) return null;

  const toggleShown = (label: string) => {
    setShown((prev) => {
      const has = prev.includes(label);
      const next = has ? prev.filter((l) => l !== label) : [...prev, label];
      // Never drop below two columns — comparison needs at least a pair.
      return next.length >= 2 ? next : prev;
    });
  };

  // ── Insertion (set-scoped) ────────────────────────────────────────────────
  const insertSections = (payload: SectionToAppend[], toastMsg: string) => {
    if (payload.length === 0) return;
    appendSections(payload);
    toast.success(toastMsg);
  };

  const insertQuestion = (label: string, sectionTitle: string, q: any) => {
    insertSections(
      [{ title: sectionTitle, setLabel: label, questions: [toEditorQuestion(q)] }],
      `Inserted 1 question from Set ${label} into the paper.`,
    );
  };

  const insertSection = (label: string, sectionTitle: string) => {
    const set = sets.find((s) => s.label === label);
    const section = (set?.result?.sections || []).find(
      (s: any) => String(s.title || "Questions") === sectionTitle,
    );
    const questions = (section?.questions || []).map(toEditorQuestion);
    insertSections(
      [{ title: sectionTitle, setLabel: label, questions }],
      `Inserted ${questions.length} question(s) — Set ${label} · ${sectionTitle}.`,
    );
  };

  const insertSet = (label: string) => {
    const set = sets.find((s) => s.label === label);
    const payload: SectionToAppend[] = (set?.result?.sections || []).map(
      (s: any) => ({
        title: String(s.title || "Questions"),
        setLabel: label,
        questions: (s.questions || []).map(toEditorQuestion),
      }),
    );
    const total = payload.reduce((n, s) => n + s.questions.length, 0);
    insertSections(payload, `Inserted all ${total} question(s) of Set ${label}.`);
  };

  const cols = effectiveShown.length;
  const gridTemplate = `repeat(${cols}, minmax(0, 1fr))`;

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-background">
      {/* ── Top bar ─────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div className="flex items-center gap-2 min-w-0">
          <Columns3 className="h-5 w-5 text-primary shrink-0" />
          <h2 className="text-base font-bold text-foreground truncate">
            Compare Sets
          </h2>
          <span className="text-[11px] text-muted-foreground hidden sm:inline">
            Aligned by blueprint slot · identical vs changed highlighted
          </span>
        </div>

        <div className="flex items-center gap-2">
          {/* Which sets to show */}
          <div className="flex items-center gap-1">
            {availableLabels.map((label) => {
              const active = effectiveShown.includes(label);
              return (
                <button
                  key={label}
                  type="button"
                  onClick={() => toggleShown(label)}
                  className={`text-xs px-2.5 py-1 rounded-md border transition-colors ${
                    active
                      ? "border-primary bg-primary/10 dark:bg-primary/10 text-primary dark:text-primary font-semibold"
                      : "border-border text-muted-foreground hover:border-zinc-400"
                  }`}
                  title={active ? `Hide Set ${label}` : `Show Set ${label}`}
                >
                  Set {label}
                </button>
              );
            })}
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setOpen(false)}
            className="h-8 text-muted-foreground"
          >
            <X className="h-4 w-4 mr-1" />
            Close
          </Button>
        </div>
      </div>

      {/* ── Column headers (Insert whole set) ───────────────────────────── */}
      <div
        className="grid gap-px border-b border-border bg-border"
        style={{ gridTemplateColumns: gridTemplate }}
      >
        {effectiveShown.map((label) => {
          const meta = sets.find((s) => s.label === label)?.result?.meta || {};
          return (
            <div
              key={label}
              className="flex items-center justify-between gap-2 bg-background px-3 py-2"
            >
              <div className="min-w-0">
                <div className="text-sm font-bold text-foreground">
                  Set {label}
                  {label === "A" && (
                    <span className="ml-1.5 text-[10px] font-normal text-muted-foreground">
                      master
                    </span>
                  )}
                </div>
                <div className="text-[10px] text-muted-foreground truncate">
                  {meta.totalQuestions ?? "—"} Q · {meta.totalMarks ?? "—"} marks
                  {label !== "A" && meta.replacedCount != null
                    ? ` · ${meta.replacedCount} changed from A`
                    : ""}
                </div>
              </div>
              <Button
                size="sm"
                onClick={() => insertSet(label)}
                className="h-7 shrink-0 bg-primary hover:bg-primary/90 text-white text-xs"
              >
                <Plus className="h-3 w-3 mr-1" />
                Insert set
              </Button>
            </div>
          );
        })}
      </div>

      {/* ── Aligned body (single scroll = inherent sync scrolling) ──────── */}
      <div className="flex-1 overflow-y-auto custom-scrollbar">
        {groups.map((group) => (
          <div key={group.title}>
            {/* Section header spanning all columns + per-set "Insert section" */}
            <div
              className="grid gap-px border-y border-border bg-border sticky top-0 z-10"
              style={{ gridTemplateColumns: gridTemplate }}
            >
              {effectiveShown.map((label) => (
                <div
                  key={label}
                  className="flex items-center justify-between gap-2 bg-muted/60 px-3 py-1.5"
                >
                  <h4 className="text-xs font-semibold text-primary dark:text-primary uppercase tracking-wider truncate">
                    {group.title}
                  </h4>
                  <button
                    type="button"
                    onClick={() => insertSection(label, group.title)}
                    className="text-[11px] text-primary hover:underline shrink-0"
                  >
                    Insert section
                  </button>
                </div>
              ))}
            </div>

            {/* Slot rows — grid keeps each set's cell the same height */}
            {group.rows.map((row) => (
              <div
                key={row.slotIndex}
                className="grid gap-px bg-border"
                style={{ gridTemplateColumns: gridTemplate }}
              >
                {effectiveShown.map((label) => {
                  const q = row.byLabel[label];
                  return (
                    <div
                      key={label}
                      className={`bg-background p-3 ${
                        row.identical
                          ? ""
                          : "ring-1 ring-inset ring-amber-300/60 dark:ring-amber-500/30 bg-amber-50/30 dark:bg-amber-950/10"
                      }`}
                    >
                      {q ? (
                        <div className="space-y-2">
                          <div className="flex items-center gap-1.5 flex-wrap text-[10px]">
                            <Badge
                              variant="outline"
                              className="font-mono bg-white dark:bg-zinc-950"
                            >
                              {q.marks}m
                            </Badge>
                            <Badge
                              variant="outline"
                              className="bg-white dark:bg-zinc-950"
                            >
                              {q.type || "—"}
                            </Badge>
                            {row.identical ? (
                              <Badge className="border-none bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
                                <CheckCircle2 className="h-3 w-3 mr-1" />
                                same
                              </Badge>
                            ) : (
                              <Badge className="border-none bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
                                changed
                              </Badge>
                            )}
                          </div>
                          <p className="text-sm text-zinc-800 dark:text-zinc-100">
                            {q.content}
                          </p>
                          {q.options && q.options.length > 0 && (
                            <div className="grid grid-cols-2 gap-1">
                              {q.options.map((opt: string, i: number) => (
                                <div
                                  key={i}
                                  className="text-[11px] text-muted-foreground border border-border p-1 rounded bg-background/50"
                                >
                                  {String.fromCharCode(65 + i)}. {opt}
                                </div>
                              ))}
                            </div>
                          )}
                          <div className="pt-1">
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() =>
                                insertQuestion(label, row.sectionTitle, q)
                              }
                              className="h-7 text-xs"
                            >
                              <Plus className="h-3 w-3 mr-1" />
                              Insert
                            </Button>
                          </div>
                        </div>
                      ) : (
                        <div className="flex h-full items-center justify-center py-4">
                          <span className="text-[11px] italic text-muted-foreground">
                            (no question in Set {label} for this slot)
                          </span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        ))}

        {groups.length === 0 && (
          <div className="flex items-center justify-center py-16">
            <p className="text-sm text-muted-foreground">
              No comparable questions in the selected sets.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
