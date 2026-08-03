"use client";

/**
 * Build Paper — a two-pane authoring workspace over the question bank.
 *
 * Left (~70%): the searchable Question Database. Every generation auto-saves
 * its whole pool, so a chapter generated once can be re-papered here with no
 * upload and no question-writing — assembly runs against saved rows only.
 *
 * Right (~30%): the Blueprint Builder — difficulty, number of sets, the CBSE
 * board blueprint, and a live distribution of the selected pool, then Generate.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  Hammer,
  Search,
  RefreshCcw,
  Zap,
  BookMarked,
  AlertTriangle,
} from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { SkeletonRows } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import {
  fetchBankSummary,
  streamPaperFromBank,
  type BankChapter,
} from "@/lib/api-client";
import { useEditorStore } from "@/store/editor-store";
import { cn } from "@/lib/utils";

// CBSE Class-10 board mark bands — the target weighting the assembler fills
// from the selected pool. Shown as the blueprint preview; the exact per-slot
// split is finalized server-side against what the pool can actually cover.
const BOARD_MARK_BANDS = [
  { marks: 1, label: "Objective / MCQ" },
  { marks: 2, label: "Very short answer" },
  { marks: 3, label: "Short answer" },
  { marks: 5, label: "Long answer" },
];

const chapterKey = (row: BankChapter) => row.chapter || row.projectName;

export default function BuildPaperPage() {
  const router = useRouter();

  const [chapters, setChapters] = useState<BankChapter[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const [difficulty, setDifficulty] = useState("medium");
  const [numSets, setNumSets] = useState(1);

  const [isBuilding, setIsBuilding] = useState(false);
  const [status, setStatus] = useState("");

  const load = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await fetchBankSummary();
      setChapters(data.chapters || []);
    } catch (error: any) {
      toast.error(error?.message || "Could not load your question bank.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const filteredChapters = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return chapters;
    return chapters.filter((row) =>
      [row.chapter, row.projectName, row.subject, row.gradeClass]
        .filter((v): v is string => typeof v === "string" && v.length > 0)
        .join(" · ")
        .toLowerCase()
        .includes(term),
    );
  }, [chapters, search]);

  const toggle = (key: string) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const selectedRows = useMemo(
    () => chapters.filter((row) => selected.has(chapterKey(row))),
    [chapters, selected],
  );

  const totalSelected = selectedRows.reduce((sum, row) => sum + row.count, 0);
  const maxSelected = Math.max(1, ...selectedRows.map((r) => r.count));

  // A paper is compiled from exactly one subject + one class.
  const subjects = new Set(selectedRows.map((r) => r.subject || ""));
  const classes = new Set(selectedRows.map((r) => r.gradeClass || ""));
  const isMixed = subjects.size > 1 || classes.size > 1;

  const allVisibleSelected =
    filteredChapters.length > 0 &&
    filteredChapters.every((r) => selected.has(chapterKey(r)));

  const toggleSelectAllVisible = () => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (allVisibleSelected) {
        filteredChapters.forEach((r) => next.delete(chapterKey(r)));
      } else {
        filteredChapters.forEach((r) => next.add(chapterKey(r)));
      }
      return next;
    });
  };

  const first = selectedRows[0];

  const handleBuild = async () => {
    if (selectedRows.length === 0) {
      toast.error("Pick at least one chapter from the database.");
      return;
    }
    if (isMixed) {
      toast.error(
        "Selected chapters span more than one subject or class. Pick from a single subject and class.",
      );
      return;
    }

    const classNumber = parseInt(
      (first.gradeClass || "10").replace(/\D/g, "") || "10",
      10,
    );

    setIsBuilding(true);
    setStatus("Loading your question bank…");

    const sections: any[] = [];
    let instructions: string[] = [];
    let doneSets: { label: string; result: any }[] | null = null;
    let failed: string | null = null;

    try {
      await streamPaperFromBank(
        {
          subject: first.subject || "",
          class: classNumber,
          chapters: selectedRows.map((r) => r.chapter).filter(Boolean),
          difficulty,
          count: -1,
          countVariation: "cbse",
          qp_type: "board",
          numberOfSets: numSets,
        },
        (event, data) => {
          if (event === "error") {
            failed = data.error || "Could not build the paper.";
          } else if (event === "status") {
            if (data.message) setStatus(data.message);
          } else if (event === "notice") {
            if (data.message) toast.info(data.message);
          } else if (event === "done" && data.result) {
            instructions = data.result.generalInstructions || [];
            for (const section of data.result.sections || []) {
              sections.push({
                title: section.title,
                questions: (section.questions || []).map((q: any) => ({
                  content: q.content,
                  type: q.type,
                  options: q.options || [],
                  answer: q.answer,
                  marks: q.marks,
                  image_url: q.image_url || q.metadata?.image_url || "",
                })),
              });
            }
            if (Array.isArray(data.sets) && data.sets.length > 1) {
              doneSets = data.sets.map((s: any) => ({
                label: s.label,
                result: s.result,
              }));
            }
          }
        },
      );

      if (failed) {
        toast.error(failed);
        return;
      }
      if (sections.length === 0) {
        toast.error("No questions could be selected for this paper.");
        return;
      }

      const store = useEditorStore.getState();
      // Set A streams into the editor doc via the append plumbing.
      if (instructions.length > 0) store.appendInstructions(instructions);
      store.appendSections(sections);
      // Sets B/C (if any) drive the editor's Set tabs / comparison workspace.
      if (doneSets) store.setComparisonSets(doneSets);
      else store.clearComparisonSets();

      const count = sections.reduce((n, s) => n + s.questions.length, 0);
      toast.success(
        `Built a ${count}-question paper${
          numSets > 1 ? ` (${numSets} sets)` : ""
        } from your question bank.`,
      );
      router.push("/editor");
    } catch (error: any) {
      toast.error(error?.message || "Could not build the paper.");
    } finally {
      setIsBuilding(false);
      setStatus("");
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col bg-background lg:flex-row">
      {/* ── Left: Question Database (~70%) ─────────────────────────────── */}
      <div className="flex min-h-0 flex-1 flex-col border-b border-border lg:border-b-0 lg:border-r">
        {/* Toolbar */}
        <div className="shrink-0 border-b border-border px-4 py-3 sm:px-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <Hammer className="h-5 w-5 text-primary" />
              <h1 className="text-lg font-semibold tracking-tight">
                Builder
              </h1>
              <span className="rounded-sm bg-muted px-1.5 py-0.5 text-xs font-medium tabular-nums text-muted-foreground">
                {isLoading ? "…" : `${chapters.length} chapters`}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <div className="relative">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                <Input
                  className="h-8 w-56 pl-8 text-sm"
                  placeholder="Search the question database…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </div>
              <button
                type="button"
                onClick={() => void load()}
                title="Refresh"
                className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-border text-muted-foreground hover:bg-accent hover:text-foreground"
              >
                <RefreshCcw className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </div>

        {/* Database table */}
        <div className="min-h-0 flex-1 overflow-auto">
          {isLoading ? (
            <SkeletonRows rows={10} height="h-9" />
          ) : chapters.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 py-24 text-center">
              <BookMarked className="empty-breathe h-10 w-10 opacity-30" />
              <p className="text-sm font-medium">Your question bank is empty.</p>
              <p className="max-w-xs text-xs text-muted-foreground">
                Generate a paper from a chapter first — every question produced
                is saved here automatically, then you can assemble more papers
                from it without uploading again.
              </p>
            </div>
          ) : filteredChapters.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-2 py-24 text-center">
              <p className="text-sm font-medium">No chapters match your search.</p>
            </div>
          ) : (
            <table className="w-full border-collapse text-sm">
              <thead className="sticky top-0 z-10 bg-muted/80 backdrop-blur">
                <tr className="border-b border-border text-left text-xs">
                  <th className="w-9 px-3 py-2">
                    <input
                      type="checkbox"
                      aria-label="Select all visible"
                      checked={allVisibleSelected}
                      onChange={toggleSelectAllVisible}
                      className="h-3.5 w-3.5 cursor-pointer accent-primary"
                    />
                  </th>
                  <th className="px-3 py-2 font-semibold text-muted-foreground">
                    Chapter
                  </th>
                  <th className="px-3 py-2 font-semibold text-muted-foreground">
                    Subject
                  </th>
                  <th className="px-3 py-2 font-semibold text-muted-foreground">
                    Class
                  </th>
                  <th className="px-3 py-2 text-right font-semibold text-muted-foreground">
                    Questions
                  </th>
                </tr>
              </thead>
              <tbody>
                {filteredChapters.map((row) => {
                  const key = chapterKey(row);
                  const isSelected = selected.has(key);
                  return (
                    <tr
                      key={row.projectId + key}
                      onClick={() => toggle(key)}
                      className={cn(
                        "cursor-pointer border-b border-border/60 transition-colors hover:bg-muted/40",
                        isSelected && "bg-accent/60",
                      )}
                    >
                      <td className="px-3 py-1.5">
                        <input
                          type="checkbox"
                          aria-label="Select chapter"
                          checked={isSelected}
                          onChange={() => toggle(key)}
                          onClick={(e) => e.stopPropagation()}
                          className="h-3.5 w-3.5 cursor-pointer accent-primary"
                        />
                      </td>
                      <td className="px-3 py-1.5 font-medium text-foreground">
                        {row.chapter || row.projectName}
                      </td>
                      <td className="px-3 py-1.5 whitespace-nowrap text-muted-foreground">
                        {row.subject || "—"}
                      </td>
                      <td className="px-3 py-1.5 whitespace-nowrap text-muted-foreground">
                        {row.gradeClass || "—"}
                      </td>
                      <td className="px-3 py-1.5 text-right tabular-nums text-muted-foreground">
                        {row.count}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* ── Right: Blueprint Builder (~30%) ────────────────────────────── */}
      <aside className="flex w-full shrink-0 flex-col lg:w-[30%] lg:min-w-[320px] lg:max-w-[440px]">
        <div className="shrink-0 border-b border-border px-5 py-3">
          <h2 className="text-sm font-semibold tracking-tight">Blueprint</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {selectedRows.length > 0
              ? `${selectedRows.length} chapter${
                  selectedRows.length === 1 ? "" : "s"
                } · ${totalSelected} questions in pool`
              : "Select chapters to compile a blueprint."}
          </p>
        </div>

        <div className="min-h-0 flex-1 space-y-5 overflow-auto px-5 py-4">
          {/* Difficulty */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-muted-foreground">
              Difficulty
            </label>
            <Select
              value={difficulty}
              onValueChange={(v) => setDifficulty(v ?? "medium")}
            >
              <SelectTrigger className="h-9 w-full text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="easy">Easy</SelectItem>
                <SelectItem value="medium">Medium</SelectItem>
                <SelectItem value="hard">Hard</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Number of sets */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-muted-foreground">
              Number of sets
            </label>
            <div className="flex gap-1.5">
              {[1, 2, 3].map((n) => (
                <button
                  key={n}
                  type="button"
                  onClick={() => setNumSets(n)}
                  className={cn(
                    "flex-1 rounded-lg border px-2 py-1.5 text-sm font-medium transition-colors",
                    numSets === n
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-border text-muted-foreground hover:bg-accent hover:text-foreground",
                  )}
                >
                  {n === 1 ? "1 set" : `${n} sets`}
                </button>
              ))}
            </div>
            <p className="text-[11px] text-muted-foreground">
              {numSets === 1
                ? "A single paper (Set A)."
                : `Parallel sets ${["A", "B", "C"]
                    .slice(0, numSets)
                    .join(", ")} — same blueprint, swapped questions.`}
            </p>
          </div>

          {/* Marks / blueprint mode */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-muted-foreground">
              Marks &amp; blueprint
            </label>
            <div className="rounded-lg border border-border bg-muted/30 px-3 py-2.5">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-foreground">
                  CBSE Board pattern
                </span>
                <span className="rounded-sm bg-primary/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-primary">
                  Auto
                </span>
              </div>
              <p className="mt-1 text-[11px] text-muted-foreground">
                Marks, sections and question mix follow the CBSE board blueprint
                for {first?.subject || "the subject"}
                {first?.gradeClass ? `, Class ${first.gradeClass}` : ""}.
              </p>
            </div>
          </div>

          {/* Distribution — mark bands (blueprint) */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-muted-foreground">
              Distribution
            </label>
            <div className="space-y-1 rounded-lg border border-border px-3 py-2.5">
              <p className="text-[11px] text-muted-foreground">
                Target mark bands (finalized from your pool):
              </p>
              {BOARD_MARK_BANDS.map((band) => (
                <div
                  key={band.marks}
                  className="flex items-center justify-between text-xs"
                >
                  <span className="text-foreground">{band.label}</span>
                  <span className="tabular-nums text-muted-foreground">
                    {band.marks} mark{band.marks === 1 ? "" : "s"}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Pool contribution per selected chapter */}
          {selectedRows.length > 0 && (
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-muted-foreground">
                Selected pool
              </label>
              <div className="space-y-1.5 rounded-lg border border-border px-3 py-2.5">
                {selectedRows.map((row) => (
                  <div key={chapterKey(row)} className="space-y-1">
                    <div className="flex items-center justify-between text-xs">
                      <span className="truncate text-foreground">
                        {row.chapter || row.projectName}
                      </span>
                      <span className="ml-2 shrink-0 tabular-nums text-muted-foreground">
                        {row.count}
                      </span>
                    </div>
                    <div className="h-1 w-full overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full rounded-full bg-primary/70"
                        style={{
                          width: `${Math.max(
                            6,
                            (row.count / maxSelected) * 100,
                          )}%`,
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {isMixed && (
            <div className="flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-[11px] text-warning">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              Selected chapters span more than one subject or class. A paper is
              compiled from a single subject and class.
            </div>
          )}
        </div>

        {/* Generate */}
        <div className="shrink-0 border-t border-border px-5 py-3">
          <button
            type="button"
            onClick={handleBuild}
            disabled={isBuilding || selectedRows.length === 0 || isMixed}
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isBuilding ? (
              <>
                <Spinner />
                {status || "Building…"}
              </>
            ) : (
              <>
                <Zap className="h-4 w-4" />
                Generate{totalSelected > 0 ? ` from ${totalSelected} questions` : ""}
              </>
            )}
          </button>
        </div>
      </aside>
    </div>
  );
}
