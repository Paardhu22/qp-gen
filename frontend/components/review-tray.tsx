"use client";

/**
 * Review tray (ISSUE 2 / Issue 3 polish) — persistent staging area for
 * freshly generated questions.
 *
 * Generation streams items into the editor store's `generatedTray`. The
 * teacher decides what reaches the paper: one at a time, multi-select,
 * insert-all, insert-by-section, or dismiss.
 *
 * Inserting a question does NOT remove it from the tray; it stays with
 * an "Inserted ✓" marker and an "Undo from paper" affordance, so the
 * tray remains an audit record of the whole generation batch. Only the
 * explicit "Dismiss" / "Clear tray" actions actually drop items.
 *
 * The grounding badge ("From sources" sparkle) was removed per teacher
 * feedback — it added visual noise on every card. We still surface the
 * "Curriculum fallback" pill, because that ungrounded state is the one
 * teachers genuinely want to spot.
 *
 * The tray itself is part of the editor store, so it survives in-app
 * navigation and reloads alongside the paper (see Issue 1).
 */
import { useMemo, useState } from "react";
import { useEditorStore, TrayItem } from "@/store/editor-store";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import {
  BookOpen,
  CheckCircle2,
  Image as ImageIcon,
  Undo2,
  X,
} from "lucide-react";

function groupBySection(items: TrayItem[]) {
  const map = new Map<string, TrayItem[]>();
  for (const item of items) {
    const list = map.get(item.sectionTitle) || [];
    list.push(item);
    map.set(item.sectionTitle, list);
  }
  // Generation is parallel, so items arrive in completion order. The
  // backend stamps metadata.slotIndex with the blueprint position —
  // sort by it so inserts respect the plan layout (e.g. Maths Section A
  // must end with the two Assertion-Reason questions at Q19–Q20).
  for (const list of map.values()) {
    list.sort(
      (a, b) =>
        (Number(a.question.metadata?.slotIndex) || Number.MAX_SAFE_INTEGER) -
        (Number(b.question.metadata?.slotIndex) || Number.MAX_SAFE_INTEGER),
    );
  }
  return Array.from(map.entries());
}

export function ReviewTray() {
  const tray = useEditorStore((s) => s.generatedTray);
  const removeFromTray = useEditorStore((s) => s.removeFromTray);
  const markTrayInserted = useEditorStore((s) => s.markTrayInserted);
  const markTrayUninserted = useEditorStore((s) => s.markTrayUninserted);
  const removeSectionFromEditor = useEditorStore(
    (s) => s.removeSectionFromEditor,
  );
  const clearTray = useEditorStore((s) => s.clearTray);
  const appendSections = useEditorStore((s) => s.appendSections);

  const [selected, setSelected] = useState<Set<string>>(new Set());

  // ── PaperPlan ordering parity ───────────────────────────────────────
  // Display sections in the order they first appeared in the tray. That
  // matches the user-declared order (Section A → B → C). Items inside
  // each section retain their insertion order. Inserted items remain
  // visible (greyed) so the tray is a complete record of the batch.
  const pending = useMemo(() => tray.filter((t) => !t.inserted), [tray]);
  const grouped = useMemo(() => groupBySection(tray), [tray]);

  if (tray.length === 0) return null;

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const insertIds = (ids: string[]) => {
    if (ids.length === 0) return;
    const itemsById = new Map(tray.map((t) => [t.id, t]));
    // Group the chosen items by section so the editor inserts each as a
    // coherent section block (the first item in a new section triggers a
    // `sectionBlock`; subsequent items in the same section are plain
    // question blocks).
    const grouped = groupBySection(
      ids
        .map((id) => itemsById.get(id))
        .filter((x): x is TrayItem => Boolean(x) && !x!.inserted),
    );

    // We must commit each section as ONE `appendSections` call to keep
    // the section header + its questions atomic in the editor's insertion
    // effect (queueMicrotask). Otherwise re-numbering races with inserts.
    appendSections(
      grouped.map(([title, items]) => ({
        title,
        questions: items.map((t) => ({
          content: t.question.content,
          type: t.question.type,
          options: t.question.options || [],
          answer: t.question.answer,
          marks: t.question.marks,
          image_url: t.question.image_url,
        })),
      })),
    );

    markTrayInserted(ids);
    setSelected(new Set());
    toast.success(
      `Inserted ${ids.length} question${ids.length === 1 ? "" : "s"} into the paper.`,
    );
  };

  const insertSingle = (id: string) => insertIds([id]);
  const insertSelected = () => insertIds(Array.from(selected));
  const insertAll = () => insertIds(pending.map((t) => t.id));
  const insertSection = (sectionTitle: string) =>
    insertIds(pending.filter((t) => t.sectionTitle === sectionTitle).map((t) => t.id));

  const dismiss = (id: string) => {
    removeFromTray(id);
    setSelected((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  };

  const undoInsert = (item: TrayItem) => {
    // Pull the question out of the paper, flip the tray marker back to
    // pending. Useful when a teacher inserts a section and then notices a
    // bad question — they undo from the tray without hunting in the doc.
    removeSectionFromEditor({
      sectionTitle: item.sectionTitle,
      content: item.question.content,
    });
    markTrayUninserted([item.id]);
    toast.message("Removed from paper. The question is back as pending.");
  };

  const insertedCount = tray.length - pending.length;

  return (
    <div className="mt-6 border-t border-border pt-6">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="text-base font-bold text-foreground flex items-center gap-2">
            Review tray
            <span className="text-[11px] font-normal text-muted-foreground">
              {pending.length} pending · {insertedCount} inserted
            </span>
          </h3>
          <p className="text-[11px] text-muted-foreground">
            Pick which generated questions go into your paper. Inserted items
            stay here as a record — use Undo to pull one back out.
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 mb-3">
        <Button
          size="sm"
          onClick={insertSelected}
          disabled={selected.size === 0}
          className="bg-primary hover:bg-primary/90 text-primary-foreground h-8"
        >
          Insert selected ({selected.size})
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={insertAll}
          disabled={pending.length === 0}
          className="h-8"
        >
          Insert all ({pending.length})
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => {
            clearTray();
            setSelected(new Set());
            toast.message("Cleared the review tray.");
          }}
          className="h-8 text-muted-foreground hover:text-foreground"
        >
          Clear tray
        </Button>
      </div>

      <div className="space-y-5">
        {grouped.map(([title, items]) => {
          const sectionPendingCount = items.filter((it) => !it.inserted).length;
          return (
            <div key={title} className="space-y-2">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-semibold text-primary dark:text-primary uppercase tracking-wider">
                  {title}{" "}
                  <span className="text-muted-foreground normal-case font-normal">
                    ({sectionPendingCount} pending · {items.length - sectionPendingCount} inserted)
                  </span>
                </h4>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => insertSection(title)}
                  disabled={sectionPendingCount === 0}
                  className="h-7 text-xs text-primary hover:bg-primary/10 dark:hover:bg-primary/10"
                >
                  Insert section
                </Button>
              </div>

              <div className="space-y-2">
                {items.map((item) => {
                  const isSelected = selected.has(item.id);
                  const isFallback = item.sourceType === "curriculum_fallback";
                  const isInserted = item.inserted;
                  // AI-drawn diagrams can be subtly wrong in ways a student
                  // will notice, so they are flagged for a teacher's eye
                  // before the paper goes out.
                  const isSyntheticImage =
                    item.sourceType === "synthetic_image" ||
                    item.question?.metadata?.syntheticImage === true;
                  return (
                    <div
                      key={item.id}
                      className={`p-3 border rounded-lg transition-colors ${
                        isInserted
                          ? "border-success/30 bg-success/10 opacity-90"
                          : isSelected
                            ? "border-primary bg-primary/60 dark:bg-primary/10"
                            : "border-border bg-muted/60 dark:bg-card/40"
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        {isInserted ? (
                          <span
                            className="mt-1 inline-flex items-center justify-center h-4 w-4 rounded-sm bg-emerald-600 text-white"
                            title="Inserted into the paper"
                            aria-label="Inserted"
                          >
                            <CheckCircle2 className="h-3 w-3" />
                          </span>
                        ) : (
                          <input
                            type="checkbox"
                            className="mt-1 rounded-sm border-border text-primary focus:ring-primary"
                            checked={isSelected}
                            onChange={() => toggleSelect(item.id)}
                          />
                        )}
                        <div className="flex-1 min-w-0">
                          <div className="flex flex-wrap items-center gap-1.5 text-[10px] mb-1.5">
                            <Badge
                              variant="outline"
                              className="font-mono bg-white dark:bg-card"
                            >
                              {item.question.marks}m
                            </Badge>
                            <Badge
                              variant="outline"
                              className="bg-white dark:bg-card"
                            >
                              {item.question.type || "—"}
                            </Badge>
                            {item.question.bloom && (
                              <Badge
                                variant="outline"
                                className="bg-white dark:bg-card"
                              >
                                {item.question.bloom}
                              </Badge>
                            )}
                            {isInserted && (
                              <Badge className="bg-emerald-100 text-emerald-700 hover:bg-emerald-100 dark:bg-emerald-900/40 dark:text-emerald-300 border-none">
                                <CheckCircle2 className="h-3 w-3 mr-1" />
                                Inserted ✓
                              </Badge>
                            )}
                            {/* Source-grounded items intentionally carry NO
                                badge — the green "From sources" sparkle was
                                removed per teacher feedback. Only the
                                ungrounded "Curriculum fallback" pill stays
                                so the teacher can spot it at a glance. */}
                            {isFallback && (
                              <Badge className="bg-amber-100 text-amber-700 hover:bg-amber-100 dark:bg-amber-900/40 dark:text-amber-300 border-none">
                                <BookOpen className="h-3 w-3 mr-1" />
                                Curriculum fallback
                              </Badge>
                            )}
                            {isSyntheticImage && (
                              <Badge
                                className="bg-accent text-accent-foreground hover:bg-accent border-none"
                                title="The diagram in this question was drawn by AI. Check it before using this paper in an exam."
                              >
                                <ImageIcon className="h-3 w-3 mr-1" />
                                AI diagram — check it
                              </Badge>
                            )}
                          </div>
                          <p className="text-sm text-foreground line-clamp-3">
                            {item.question.content}
                          </p>
                          {item.question.options && item.question.options.length > 0 && (
                            <div className="grid grid-cols-2 gap-1 mt-2">
                              {item.question.options.map((opt, idx) => (
                                <div
                                  key={idx}
                                  className="text-[11px] text-muted-foreground border border-border p-1 rounded-sm bg-white/70 dark:bg-card/40"
                                >
                                  {String.fromCharCode(65 + idx)}. {opt}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                        <div className="flex flex-col gap-1 flex-shrink-0">
                          {isInserted ? (
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => undoInsert(item)}
                              className="h-7 px-2 text-xs text-muted-foreground hover:text-amber-600"
                            >
                              <Undo2 className="h-3.5 w-3.5 mr-1" />
                              Undo
                            </Button>
                          ) : (
                            <>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => insertSingle(item.id)}
                                className="h-7 px-2 text-xs"
                              >
                                <CheckCircle2 className="h-3.5 w-3.5 mr-1" />
                                Insert
                              </Button>
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => dismiss(item.id)}
                                className="h-7 px-2 text-xs text-muted-foreground hover:text-red-600"
                              >
                                <X className="h-3.5 w-3.5 mr-1" />
                                Dismiss
                              </Button>
                            </>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      {insertedCount > 0 && pending.length === 0 && (
        <div className="mt-4 text-xs text-muted-foreground italic">
          All generated questions are in the paper.{" "}
          <button
            className="underline text-primary hover:text-primary"
            onClick={() => {
              clearTray();
              toast.message("Cleared the review tray.");
            }}
          >
            Clear tray
          </button>
        </div>
      )}
    </div>
  );
}
