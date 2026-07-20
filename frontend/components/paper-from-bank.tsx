"use client";

/**
 * Create a paper from questions already in the bank.
 *
 * Every generation auto-saves its whole question pool (~80 questions, not just
 * the ~38 the paper used). Once a chapter has been generated, building another
 * paper from it needs no chapter upload and no question writing — the backend
 * runs assembly against the saved questions and nothing else. That is roughly
 * two orders of magnitude cheaper than a fresh generation, and near-instant.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  BookMarked,
  Check,
  Loader2,
  RefreshCcw,
  Sparkles,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  fetchBankSummary,
  streamPaperFromBank,
  type BankChapter,
} from "@/lib/api-client";
import { useEditorStore } from "@/store/editor-store";
import { cn } from "@/lib/utils";

type Props = {
  /** Rendered inline in a page; the caller controls placement. */
  className?: string;
};

export function PaperFromBank({ className }: Props) {
  const router = useRouter();

  const [chapters, setChapters] = useState<BankChapter[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [difficulty, setDifficulty] = useState("medium");
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

  const toggle = (key: string) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const chapterKey = (row: BankChapter) => row.chapter || row.projectName;

  const selectedRows = useMemo(
    () => chapters.filter((row) => selected.has(chapterKey(row))),
    [chapters, selected],
  );

  const totalSelected = selectedRows.reduce((sum, row) => sum + row.count, 0);

  // Every selected chapter must share one subject/class — a paper cannot mix
  // Class 9 Science with Class 10 Maths, and the blueprint is compiled from
  // exactly one of each.
  const subjects = new Set(selectedRows.map((r) => r.subject || ""));
  const classes = new Set(selectedRows.map((r) => r.gradeClass || ""));
  const isMixed = subjects.size > 1 || classes.size > 1;

  const handleBuild = async () => {
    if (selectedRows.length === 0) {
      toast.error("Pick at least one chapter.");
      return;
    }
    if (isMixed) {
      toast.error(
        "Selected chapters span more than one subject or class. Pick chapters from a single subject and class.",
      );
      return;
    }

    const first = selectedRows[0];
    const classNumber = parseInt(
      (first.gradeClass || "10").replace(/\D/g, "") || "10",
      10,
    );

    setIsBuilding(true);
    setStatus("Loading your saved questions…");

    const sections: any[] = [];
    let instructions: string[] = [];
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
      if (instructions.length > 0) store.appendInstructions(instructions);
      store.appendSections(sections);

      const count = sections.reduce((n, s) => n + s.questions.length, 0);
      toast.success(`Built a ${count}-question paper from your saved questions.`);
      router.push("/editor");
    } catch (error: any) {
      toast.error(error?.message || "Could not build the paper.");
    } finally {
      setIsBuilding(false);
      setStatus("");
    }
  };

  if (isLoading) {
    return (
      <div
        className={cn(
          "rounded-xl border border-border bg-card p-5 flex items-center gap-2 text-sm text-muted-foreground",
          className,
        )}
      >
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading your question bank…
      </div>
    );
  }

  if (chapters.length === 0) {
    return (
      <div
        className={cn(
          "rounded-xl border border-dashed border-border bg-card p-5",
          className,
        )}
      >
        <div className="flex items-center gap-2 mb-1">
          <BookMarked className="h-4 w-4 text-muted-foreground" />
          <h2 className="text-sm font-semibold">Create from saved questions</h2>
        </div>
        <p className="text-sm text-muted-foreground">
          Your question bank is empty. Generate a paper from a chapter first —
          every question produced is saved here automatically, and you can build
          more papers from them without uploading the chapter again.
        </p>
      </div>
    );
  }

  return (
    <div className={cn("rounded-xl border border-border bg-card p-5", className)}>
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <div className="flex items-center gap-2">
            <BookMarked className="h-4 w-4 text-indigo-600 dark:text-indigo-400" />
            <h2 className="text-sm font-semibold">
              Create from saved questions
            </h2>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            Build a new paper from chapters you have already generated — no
            upload, no waiting for questions to be written.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="text-muted-foreground hover:text-foreground transition-colors"
          title="Refresh"
        >
          <RefreshCcw className="h-4 w-4" />
        </button>
      </div>

      <div className="space-y-1.5 max-h-56 overflow-y-auto custom-scrollbar mb-3">
        {chapters.map((row) => {
          const key = chapterKey(row);
          const isSelected = selected.has(key);
          return (
            <button
              key={row.projectId + key}
              type="button"
              onClick={() => toggle(key)}
              className={cn(
                "w-full flex items-center gap-2.5 rounded-lg border px-3 py-2 text-left transition-colors",
                isSelected
                  ? "border-indigo-500 bg-indigo-50/60 dark:bg-indigo-500/10"
                  : "border-border hover:bg-muted/50",
              )}
            >
              <span
                className={cn(
                  "inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-sm border",
                  isSelected
                    ? "bg-indigo-600 border-indigo-600 text-white"
                    : "border-muted-foreground/40",
                )}
              >
                {isSelected && <Check className="h-3 w-3" />}
              </span>
              <span className="flex-1 min-w-0">
                <span className="block text-sm truncate">
                  {row.chapter || row.projectName}
                </span>
                <span className="block text-[11px] text-muted-foreground truncate">
                  {[row.subject, row.gradeClass && `Class ${row.gradeClass}`]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
              </span>
              <span className="text-xs font-medium text-muted-foreground shrink-0">
                {row.count}
              </span>
            </button>
          );
        })}
      </div>

      {isMixed && (
        <p className="text-xs text-amber-600 dark:text-amber-400 mb-2">
          Selected chapters span more than one subject or class. Pick chapters
          from a single subject and class.
        </p>
      )}

      <div className="flex items-center gap-2">
        <Select
          value={difficulty}
          onValueChange={(value) => setDifficulty(value ?? "medium")}
        >
          <SelectTrigger className="w-32 h-9 text-sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="easy">Easy</SelectItem>
            <SelectItem value="medium">Medium</SelectItem>
            <SelectItem value="hard">Hard</SelectItem>
          </SelectContent>
        </Select>

        <Button
          onClick={handleBuild}
          disabled={isBuilding || selectedRows.length === 0 || isMixed}
          className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white gap-2"
        >
          {isBuilding ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              {status || "Building…"}
            </>
          ) : (
            <>
              <Sparkles className="h-4 w-4" />
              Create paper
              {totalSelected > 0 && ` from ${totalSelected} questions`}
            </>
          )}
        </Button>
      </div>
    </div>
  );
}

export default PaperFromBank;
