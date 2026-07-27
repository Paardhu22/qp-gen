"use client";

/**
 * Comparison Workspace — reviewing a multi-set generation (Sets A / B / C
 * produced in one SSE run).
 *
 * Two or three sets are shown side by side, aligned row-for-row by the
 * blueprint slot index so sections and marks line up horizontally and one
 * scrollbar keeps every column in sync. Questions identical across the shown
 * sets are marked "same"; questions that differ are highlighted "changed".
 *
 * This view reviews. It does not insert.
 *
 * It used to carry Insert Single / Insert Section / Insert Set for each of A,
 * B and C, routed through `appendSections` with a set label so headers read
 * "Set B · Section A" and two sets could share one document without merging.
 * That whole mechanism existed to work around a problem the editor no longer
 * has: it has a tab per set. Approving now hands each set to its own tab
 * directly, so a teacher who likes the paper clicks once instead of three
 * times per set, and two sets can never end up in one document.
 *
 * What replaced it is per-question control — Edit, Delete and Replace — which
 * is what "I like the paper but not question 7" actually needs. Replace
 * regenerates exactly that slot (same marks, type, section, chapter,
 * difficulty, generator) and leaves every other question untouched.
 */
import { useEffect, useMemo, useState } from "react";
import {
  useEditorStore,
  type ComparisonSet,
} from "@/store/editor-store";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { replaceQuestion, ApiError } from "@/lib/api-client";
import {
  Check,
  CheckCircle2,
  Columns3,
  Loader2,
  Pencil,
  RefreshCw,
  Trash2,
  X,
} from "lucide-react";

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
function buildGroups(sets: ComparisonSet[], shown: string[]): SectionGroup[] {
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
      const present = shown.map((l) => e.byLabel[l]).filter((q) => q != null);
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
    .sort((a: any, b: any) => a.slotIndex - b.slotIndex || a._order - b._order);

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

/**
 * The blueprint identity of a question, for the replace call.
 *
 * Everything here comes from the metadata the backend already stamps on every
 * generated question, so a replacement is matched against the same slot the
 * original filled rather than against a guess.
 */
function slotFor(q: any, sectionTitle: string) {
  const meta = q?.metadata || {};
  return {
    slotIndex: Number(meta.slotIndex) || 0,
    section: String(meta.section || sectionTitle || ""),
    marks: Number(q?.marks) || 1,
    type: String(q?.type || ""),
    generator: String(meta.generator || "question_pool"),
    assetType: String(meta.assetType || ""),
    chapter: String(meta.inferredChapter || meta.chapterTitle || ""),
    topic: String(meta.inferredTopic || ""),
    difficulty: String(meta.difficulty || ""),
    subject: String(meta.subject || ""),
    poolId: String(meta.poolId || ""),
    questionId: String(meta.questionId || ""),
  };
}

/** Every question id currently on any set — never offer one of them back. */
function usedQuestionIds(sets: ComparisonSet[]): string[] {
  const ids = new Set<string>();
  sets.forEach((set) =>
    (set.result?.sections || []).forEach((section: any) =>
      (section.questions || []).forEach((q: any) => {
        const id = q?.metadata?.questionId;
        if (id) ids.add(String(id));
      }),
    ),
  );
  return Array.from(ids);
}

export function ComparisonWorkspace() {
  const sets = useEditorStore((s) => s.comparisonSets);
  const open = useEditorStore((s) => s.comparisonOpen);
  const setOpen = useEditorStore((s) => s.setComparisonOpen);
  const replaceInSet = useEditorStore((s) => s.replaceComparisonQuestion);
  const removeFromSet = useEditorStore((s) => s.removeComparisonQuestion);
  const approveSets = useEditorStore((s) => s.approveComparisonSets);

  const availableLabels = useMemo(() => sets.map((s) => s.label), [sets]);
  const [shown, setShown] = useState<string[]>(availableLabels);

  // Which cell is being edited / replaced, keyed "label:slotIndex".
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState<Record<string, boolean>>({});

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

  // Esc closes the overlay — it is full-screen and modal, so a keyboard exit
  // matters more here than anywhere else in the app.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !editing) setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, editing, setOpen]);

  if (!open || sets.length < 2) return null;

  const toggleShown = (label: string) => {
    setShown((prev) => {
      const has = prev.includes(label);
      const next = has ? prev.filter((l) => l !== label) : [...prev, label];
      // Never drop below two columns — comparison needs at least a pair.
      return next.length >= 2 ? next : prev;
    });
  };

  const cellKey = (label: string, slotIndex: number) => `${label}:${slotIndex}`;

  // ── Per-question actions ──────────────────────────────────────────────────

  const startEdit = (label: string, slotIndex: number, content: string) => {
    setEditing(cellKey(label, slotIndex));
    setDraft(content);
  };

  const commitEdit = (label: string, slotIndex: number) => {
    const text = draft.trim();
    if (!text) {
      toast.error("A question cannot be empty.");
      return;
    }
    replaceInSet(label, slotIndex, { content: text });
    setEditing(null);
    setDraft("");
  };

  const deleteQuestion = (label: string, slotIndex: number) => {
    removeFromSet(label, slotIndex);
    toast.success(`Removed question ${slotIndex} from Set ${label}.`);
  };

  const doReplace = async (
    label: string,
    slotIndex: number,
    sectionTitle: string,
    question: any,
  ) => {
    const key = cellKey(label, slotIndex);
    setBusy((b) => ({ ...b, [key]: true }));
    try {
      const { question: next, source } = await replaceQuestion(
        slotFor(question, sectionTitle),
        { excludeIds: usedQuestionIds(sets) },
      );
      replaceInSet(label, slotIndex, next);
      toast.success(
        source === "bank"
          ? `Swapped in another question from your bank (Set ${label}, Q${slotIndex}).`
          : `Wrote a new question for Set ${label}, Q${slotIndex}.`,
      );
    } catch (error) {
      const message =
        error instanceof ApiError && error.status === 409
          ? "No other question fits this slot yet. Generate more for this chapter first."
          : error instanceof Error
            ? error.message
            : "Could not replace this question.";
      toast.error(message);
    } finally {
      setBusy((b) => ({ ...b, [key]: false }));
    }
  };

  const approve = () => {
    approveSets();
    toast.success(
      sets.length > 1
        ? `Approved — Sets ${sets.map((s) => s.label).join(", ")} are now in their tabs.`
        : "Approved — the paper is now in the editor.",
    );
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
            Review Sets
          </h2>
          <span className="text-[11px] text-muted-foreground hidden sm:inline">
            Aligned by blueprint slot · edit, delete or replace any question
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
            size="sm"
            onClick={approve}
            className="h-8 bg-primary hover:bg-primary/90 text-white text-xs font-semibold"
            title="Put every set into its own editor tab"
          >
            <Check className="h-4 w-4 mr-1" />
            Approve &amp; open in editor
          </Button>
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

      {/* ── Column headers ──────────────────────────────────────────────── */}
      <div
        className="grid gap-px border-b border-border bg-border"
        style={{ gridTemplateColumns: gridTemplate }}
      >
        {effectiveShown.map((label) => {
          const meta = sets.find((s) => s.label === label)?.result?.meta || {};
          return (
            <div key={label} className="bg-background px-3 py-2">
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
          );
        })}
      </div>

      {/* ── Aligned body (single scroll = inherent sync scrolling) ──────── */}
      <div className="flex-1 overflow-y-auto custom-scrollbar">
        {groups.map((group) => (
          <div key={group.title}>
            {/* Section header spanning all columns */}
            <div
              className="grid gap-px border-y border-border bg-border sticky top-0 z-10"
              style={{ gridTemplateColumns: gridTemplate }}
            >
              {effectiveShown.map((label) => (
                <div key={label} className="bg-muted/60 px-3 py-1.5">
                  <h4 className="text-xs font-semibold text-primary dark:text-primary uppercase tracking-wider truncate">
                    {group.title}
                  </h4>
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
                  const key = cellKey(label, row.slotIndex);
                  const isEditing = editing === key;
                  const isBusy = !!busy[key];

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
                              Q{row.slotIndex} · {q.marks}m
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

                          {isEditing ? (
                            <div className="space-y-2">
                              <Textarea
                                value={draft}
                                onChange={(e) => setDraft(e.target.value)}
                                rows={6}
                                className="text-sm"
                                autoFocus
                              />
                              <div className="flex gap-1.5">
                                <Button
                                  size="sm"
                                  onClick={() => commitEdit(label, row.slotIndex)}
                                  className="h-7 text-xs"
                                >
                                  Save
                                </Button>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  onClick={() => {
                                    setEditing(null);
                                    setDraft("");
                                  }}
                                  className="h-7 text-xs"
                                >
                                  Cancel
                                </Button>
                              </div>
                            </div>
                          ) : (
                            <>
                              <p className="text-sm whitespace-pre-wrap text-zinc-800 dark:text-zinc-100">
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
                              <div className="flex items-center gap-1 pt-1">
                                <Button
                                  size="sm"
                                  variant="outline"
                                  disabled={isBusy}
                                  onClick={() =>
                                    doReplace(
                                      label,
                                      row.slotIndex,
                                      row.sectionTitle,
                                      q,
                                    )
                                  }
                                  className="h-7 text-xs"
                                  title="Regenerate only this question, keeping its marks, type and section"
                                >
                                  {isBusy ? (
                                    <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                                  ) : (
                                    <RefreshCw className="h-3 w-3 mr-1" />
                                  )}
                                  Replace
                                </Button>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  disabled={isBusy}
                                  onClick={() =>
                                    startEdit(label, row.slotIndex, q.content)
                                  }
                                  className="h-7 text-xs"
                                  title="Edit this question"
                                >
                                  <Pencil className="h-3 w-3 mr-1" />
                                  Edit
                                </Button>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  disabled={isBusy}
                                  onClick={() =>
                                    deleteQuestion(label, row.slotIndex)
                                  }
                                  className="h-7 text-xs text-destructive hover:text-destructive"
                                  title="Delete this question from this set"
                                >
                                  <Trash2 className="h-3 w-3" />
                                </Button>
                              </div>
                            </>
                          )}
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
