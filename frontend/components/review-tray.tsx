"use client";

/**
 * Review tray (ISSUE 2) — staging area for freshly generated questions.
 *
 * Generation streams items into the editor store's `generatedTray`. The
 * teacher decides what reaches the paper: one at a time, multi-select,
 * insert-all, insert-by-section, or dismiss. Every tray item carries a
 * source-type badge ("From sources" vs "Curriculum fallback") so
 * ungrounded questions are easy to skip.
 *
 * The tray itself is part of the editor store, so it survives in-app
 * navigation and reloads alongside the paper (see Issue 1).
 */
import { useMemo, useState } from "react";
import { useEditorStore, TrayItem } from "@/store/editor-store";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { CheckCircle2, X, Sparkles, BookOpen } from "lucide-react";

function groupBySection(items: TrayItem[]) {
  const map = new Map<string, TrayItem[]>();
  for (const item of items) {
    const list = map.get(item.sectionTitle) || [];
    list.push(item);
    map.set(item.sectionTitle, list);
  }
  return Array.from(map.entries());
}

export function ReviewTray() {
  const tray = useEditorStore((s) => s.generatedTray);
  const removeFromTray = useEditorStore((s) => s.removeFromTray);
  const markTrayInserted = useEditorStore((s) => s.markTrayInserted);
  const clearTray = useEditorStore((s) => s.clearTray);
  const appendSections = useEditorStore((s) => s.appendSections);

  const [selected, setSelected] = useState<Set<string>>(new Set());

  const pending = useMemo(() => tray.filter((t) => !t.inserted), [tray]);
  const sections = useMemo(() => groupBySection(pending), [pending]);

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

  const insertedCount = tray.length - pending.length;

  return (
    <div className="mt-6 border-t border-zinc-200 dark:border-zinc-800 pt-6">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="text-base font-bold text-zinc-900 dark:text-white flex items-center gap-2">
            Review tray
            <span className="text-[11px] font-normal text-zinc-500">
              {pending.length} pending · {insertedCount} inserted
            </span>
          </h3>
          <p className="text-[11px] text-zinc-500">
            Pick which generated questions go into your paper. Nothing here has
            been inserted yet.
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 mb-3">
        <Button
          size="sm"
          onClick={insertSelected}
          disabled={selected.size === 0}
          className="bg-indigo-600 hover:bg-indigo-700 text-white h-8"
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
          className="h-8 text-zinc-500 hover:text-zinc-700"
        >
          Clear tray
        </Button>
      </div>

      <div className="space-y-5">
        {sections.map(([title, items]) => (
          <div key={title} className="space-y-2">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-semibold text-indigo-600 dark:text-indigo-400 uppercase tracking-wider">
                {title}{" "}
                <span className="text-zinc-400 normal-case font-normal">
                  ({items.length})
                </span>
              </h4>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => insertSection(title)}
                className="h-7 text-xs text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-500/10"
              >
                Insert section
              </Button>
            </div>

            <div className="space-y-2">
              {items.map((item) => {
                const isSelected = selected.has(item.id);
                const isFallback = item.sourceType === "curriculum_fallback";
                return (
                  <div
                    key={item.id}
                    className={`p-3 border rounded-lg transition-colors ${
                      isSelected
                        ? "border-indigo-500 bg-indigo-50/60 dark:bg-indigo-500/10"
                        : "border-zinc-200 dark:border-zinc-800 bg-zinc-50/60 dark:bg-zinc-900/40"
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <input
                        type="checkbox"
                        className="mt-1 rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500"
                        checked={isSelected}
                        onChange={() => toggleSelect(item.id)}
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex flex-wrap items-center gap-1.5 text-[10px] mb-1.5">
                          <Badge
                            variant="outline"
                            className="font-mono bg-white dark:bg-zinc-950"
                          >
                            {item.question.marks}m
                          </Badge>
                          <Badge
                            variant="outline"
                            className="bg-white dark:bg-zinc-950"
                          >
                            {item.question.type || "—"}
                          </Badge>
                          {item.question.bloom && (
                            <Badge
                              variant="outline"
                              className="bg-white dark:bg-zinc-950"
                            >
                              {item.question.bloom}
                            </Badge>
                          )}
                          {isFallback ? (
                            <Badge className="bg-amber-100 text-amber-700 hover:bg-amber-100 dark:bg-amber-900/40 dark:text-amber-300 border-none">
                              <BookOpen className="h-3 w-3 mr-1" />
                              Curriculum fallback
                            </Badge>
                          ) : item.sourceType === "rag" ? (
                            <Badge className="bg-emerald-100 text-emerald-700 hover:bg-emerald-100 dark:bg-emerald-900/40 dark:text-emerald-300 border-none">
                              <Sparkles className="h-3 w-3 mr-1" />
                              From sources
                            </Badge>
                          ) : null}
                        </div>
                        <p className="text-sm text-zinc-800 dark:text-zinc-100 line-clamp-3">
                          {item.question.content}
                        </p>
                        {item.question.options && item.question.options.length > 0 && (
                          <div className="grid grid-cols-2 gap-1 mt-2">
                            {item.question.options.map((opt, idx) => (
                              <div
                                key={idx}
                                className="text-[11px] text-zinc-500 dark:text-zinc-400 border border-zinc-200 dark:border-zinc-800 p-1 rounded bg-white/70 dark:bg-zinc-950/40"
                              >
                                {String.fromCharCode(65 + idx)}. {opt}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                      <div className="flex flex-col gap-1 flex-shrink-0">
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
                          className="h-7 px-2 text-xs text-zinc-500 hover:text-red-600"
                        >
                          <X className="h-3.5 w-3.5 mr-1" />
                          Dismiss
                        </Button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {insertedCount > 0 && pending.length === 0 && (
        <div className="mt-4 text-xs text-zinc-500 italic">
          All generated questions have been inserted.{" "}
          <button
            className="underline text-indigo-600 hover:text-indigo-700"
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
