"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  BookOpen,
  Loader2,
  AlertCircle,
  CheckCircle2,
  ChevronLeft,
} from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { fetchJson, ApiError } from "@/lib/api-client";
import { toast } from "sonner";

export type HsatBookStatus =
  | "not_ingested"
  | "pending"
  | "processing"
  | "ready"
  | "error";

interface HsatChapterEntry {
  s3_key: string;
  label: string;
  status: HsatBookStatus;
  error?: string | null;
}

interface HsatBookEntry {
  chapter_count: number;
  status: HsatBookStatus;
  chunk_count: number;
  error?: string | null;
  processed_at?: string | null;
  chapters?: HsatChapterEntry[];
}

interface HsatCatalogResponse {
  enabled: boolean;
  message?: string | null;
  tree: Record<string, Record<string, Record<string, HsatBookEntry>>>;
}

interface HsatChaptersResponse {
  grade: string;
  subject: string;
  book: string;
  chapters: HsatChapterEntry[];
  status: HsatBookStatus;
  chunk_count: number;
  error?: string | null;
}

interface HsatIngestResponse {
  hsat_source_id: string;
  grade: string;
  subject: string;
  book: string;
  status: HsatBookStatus;
  chunk_count: number;
}

export interface AppliedHsatSource {
  id: string;
  grade: string;
  subject: string;
  book: string;
  status: HsatBookStatus;
  chunkCount: number;
  selectedChapterCount?: number;
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  paperId?: string | null;
  appliedIds: string[];
  onApply: (source: AppliedHsatSource) => void;
}

type Step = "select" | "chapters";

export function HsatSourcePicker({
  open,
  onOpenChange,
  paperId,
  appliedIds,
  onApply,
}: Props) {
  const [catalog, setCatalog] = useState<HsatCatalogResponse | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [grade, setGrade] = useState<string>("");
  const [subject, setSubject] = useState<string>("");
  const [book, setBook] = useState<string>("");
  const [step, setStep] = useState<Step>("select");
  const [chapters, setChapters] = useState<HsatChapterEntry[]>([]);
  const [chaptersLoading, setChaptersLoading] = useState(false);
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [isWorking, setIsWorking] = useState(false);

  // Reset transient state every time the modal is closed so a re-open
  // doesn't ship stale selections.
  useEffect(() => {
    if (!open) {
      setIsWorking(false);
      setStep("select");
      setChapters([]);
      setSelectedKeys(new Set());
    }
  }, [open]);

  const fetchCatalog = useCallback(async () => {
    try {
      setCatalogError(null);
      const data = await fetchJson<HsatCatalogResponse>("/api/hsat/catalog/");
      setCatalog(data);
      // Default the selectors to the first available option so the modal
      // is never empty after the initial load.
      const grades = Object.keys(data.tree);
      if (grades.length > 0 && !grade) {
        const g = grades[0];
        setGrade(g);
        const subjects = Object.keys(data.tree[g] ?? {});
        if (subjects.length > 0 && !subject) {
          const s = subjects[0];
          setSubject(s);
          const books = Object.keys(data.tree[g][s] ?? {});
          if (books.length > 0 && !book) {
            setBook(books[0]);
          }
        }
      }
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Could not load HSAT catalog.";
      setCatalogError(message);
    }
  }, [grade, subject, book]);

  useEffect(() => {
    if (!open) return;
    void fetchCatalog();
  }, [open, fetchCatalog]);

  const gradeOptions = useMemo(
    () => Object.keys(catalog?.tree ?? {}),
    [catalog],
  );
  const subjectOptions = useMemo(
    () => (grade ? Object.keys(catalog?.tree?.[grade] ?? {}) : []),
    [catalog, grade],
  );
  const bookOptions = useMemo(
    () => (grade && subject ? Object.keys(catalog?.tree?.[grade]?.[subject] ?? {}) : []),
    [catalog, grade, subject],
  );

  // When the chosen subject has exactly one book, skip the Book dropdown
  // and pick it automatically (the user shouldn't need a redundant tap).
  useEffect(() => {
    if (bookOptions.length === 1 && book !== bookOptions[0]) {
      setBook(bookOptions[0]);
    }
  }, [bookOptions, book]);

  const selectedBookEntry: HsatBookEntry | undefined =
    grade && subject && book
      ? catalog?.tree?.[grade]?.[subject]?.[book]
      : undefined;

  const fetchChapters = useCallback(async () => {
    if (!grade || !subject || !book) return;
    setChaptersLoading(true);
    try {
      const params = new URLSearchParams({ grade, subject, book });
      const data = await fetchJson<HsatChaptersResponse>(
        `/api/hsat/chapters/?${params.toString()}`,
      );
      setChapters(data.chapters || []);
      // Nothing is pre-selected. Pre-selecting the whole book meant a
      // teacher who wanted one chapter kicked off a fourteen-chapter
      // ingest by pressing the obvious button — the single biggest cause
      // of "applying a source takes forever". Chapters already indexed
      // cost nothing to re-tick, so start from what they actually want.
      setSelectedKeys(
        new Set(
          (data.chapters || [])
            .filter((c) => c.status === "ready")
            .map((c) => c.s3_key),
        ),
      );
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "Could not load chapter list.",
      );
    } finally {
      setChaptersLoading(false);
    }
  }, [grade, subject, book]);

  const handleNextToChapters = async () => {
    if (!grade || !subject || !book) return;
    setStep("chapters");
    await fetchChapters();
  };

  const handleGradeChange = (value: string | null) => {
    const next = value ?? "";
    setGrade(next);
    const subjects = Object.keys(catalog?.tree?.[next] ?? {});
    const nextSubject = subjects[0] ?? "";
    setSubject(nextSubject);
    const books = nextSubject
      ? Object.keys(catalog?.tree?.[next]?.[nextSubject] ?? {})
      : [];
    setBook(books[0] ?? "");
  };

  const handleSubjectChange = (value: string | null) => {
    const next = value ?? "";
    setSubject(next);
    const books = Object.keys(catalog?.tree?.[grade]?.[next] ?? {});
    setBook(books[0] ?? "");
  };

  const handleBookChange = (value: string | null) => {
    setBook(value ?? "");
  };

  const toggleChapter = (key: string) => {
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const selectAllChapters = () =>
    setSelectedKeys(new Set(chapters.map((c) => c.s3_key)));
  const deselectAllChapters = () => setSelectedKeys(new Set());

  /**
   * Apply the book and get out of the way.
   *
   * This used to hold the dialog open — spinner, "Preparing…", disabled
   * buttons — polling the catalog on a 10-30 s backoff until the whole book
   * finished indexing, which for a first-use textbook is minutes of a modal
   * a teacher can do nothing with. Nothing about that wait was necessary:
   * `/api/hsat/ingest/` already returns the moment the background thread is
   * spawned, and the source is applied to the paper by id, not by readiness.
   *
   * So the dialog now closes immediately. The applied source renders as a
   * "Preparing this book…" row in the Sources panel, `useHsatReadiness`
   * flips it to ready when the chunks land, and `services/source_readiness`
   * remains the authoritative gate that refuses to generate from a source
   * that isn't there yet. The teacher configures the rest of the paper while
   * the book indexes instead of watching it.
   */
  const handleConfirm = async () => {
    if (!grade || !subject || !book) return;
    if (chapters.length > 0 && selectedKeys.size === 0) {
      toast.error("Select at least one chapter.");
      return;
    }
    setIsWorking(true);

    const chapterKeysList =
      chapters.length > 0 ? Array.from(selectedKeys) : undefined;

    try {
      const ingest = await fetchJson<HsatIngestResponse>("/api/hsat/ingest/", {
        method: "POST",
        body: JSON.stringify({
          grade,
          subject,
          book,
          chapter_keys: chapterKeysList,
        }),
      });

      if (paperId) {
        try {
          await fetchJson<HsatIngestResponse>("/api/hsat/apply/", {
            method: "POST",
            body: JSON.stringify({
              paper_id: paperId,
              grade,
              subject,
              book,
              chapter_keys: chapterKeysList,
            }),
          });
        } catch (err) {
          toast.error(
            err instanceof ApiError
              ? err.message
              : "Could not link the HSAT source to this paper.",
          );
          setIsWorking(false);
          return;
        }
      }

      onApply({
        id: ingest.hsat_source_id,
        grade,
        subject,
        book,
        status: ingest.status,
        chunkCount: ingest.chunk_count,
        selectedChapterCount: chapterKeysList?.length,
      });

      if (ingest.status !== "ready") {
        toast.success(
          `${book} added — the chapters you picked are being read in the background.`,
        );
      }

      setIsWorking(false);
      onOpenChange(false);
    } catch (err) {
      setIsWorking(false);
      toast.error(
        err instanceof ApiError ? err.message : "Could not start HSAT ingestion.",
      );
    }
  };

  const statusLabel = (entry?: HsatBookEntry) => {
    if (!entry) return null;
    if (entry.status === "ready") {
      return (
        <span className="inline-flex items-center gap-1 text-green-600 dark:text-green-400">
          <CheckCircle2 className="h-3.5 w-3.5" />
          Ready ({entry.chunk_count.toLocaleString()} chunks)
        </span>
      );
    }
    if (entry.status === "processing" || entry.status === "pending") {
      return (
        <span className="inline-flex items-center gap-1 text-primary dark:text-primary">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          Preparing — first use only
        </span>
      );
    }
    if (entry.status === "error") {
      return (
        <span className="inline-flex items-center gap-1 text-red-500 dark:text-red-400">
          <AlertCircle className="h-3.5 w-3.5" />
          Error — try again
        </span>
      );
    }
    return (
      <span className="text-muted-foreground">
        {entry.chapter_count} chapters · not yet indexed
      </span>
    );
  };

  const subjectHasOneBook = bookOptions.length === 1;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {step === "chapters" && (
              <button
                type="button"
                className="text-muted-foreground hover:text-foreground"
                onClick={() => setStep("select")}
                title="Back"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
            )}
            <BookOpen className="h-4 w-4 text-primary" />
            {step === "select"
              ? "Apply Source from HSAT"
              : `Chapters — ${book}`}
          </DialogTitle>
          <DialogDescription>
            {step === "select"
              ? "Pick a CBSE textbook. Each chapter is read once for everyone — after that it is instant."
              : "Tick only the chapters this paper covers. Ones already read are ticked for you; new ones are read in the background, so you can carry on."}
          </DialogDescription>
        </DialogHeader>

        {catalogError && (
          <div className="rounded-md border border-red-200 dark:border-red-900/40 bg-red-50 dark:bg-red-950/20 p-3 text-xs text-red-600 dark:text-red-300">
            {catalogError}
          </div>
        )}

        {catalog && catalog.enabled === false && (
          <div className="rounded-md border border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-950/20 p-3 text-xs text-amber-700 dark:text-amber-200">
            {catalog.message ??
              "HSAT sources are not available — AWS S3 is not configured on the backend."}
          </div>
        )}

        {step === "select" && catalog && catalog.enabled !== false && (
          <div className="space-y-3">
            <div>
              <label className="text-xs font-medium text-muted-foreground">
                Grade
              </label>
              <Select
                value={grade}
                onValueChange={handleGradeChange}
                disabled={isWorking || gradeOptions.length === 0}
              >
                <SelectTrigger className="w-full mt-1">
                  <SelectValue placeholder="Select grade" />
                </SelectTrigger>
                <SelectContent>
                  {gradeOptions.map((g) => (
                    <SelectItem key={g} value={g}>
                      Class {g}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <label className="text-xs font-medium text-muted-foreground">
                Subject
              </label>
              <Select
                value={subject}
                onValueChange={handleSubjectChange}
                disabled={isWorking || subjectOptions.length === 0}
              >
                <SelectTrigger className="w-full mt-1">
                  <SelectValue placeholder="Select subject" />
                </SelectTrigger>
                <SelectContent>
                  {subjectOptions.map((s) => (
                    <SelectItem key={s} value={s}>
                      {s}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {!subjectHasOneBook && (
              <div>
                <label className="text-xs font-medium text-muted-foreground">
                  Book
                </label>
                <Select
                  value={book}
                  onValueChange={handleBookChange}
                  disabled={isWorking || bookOptions.length === 0}
                >
                  <SelectTrigger className="w-full mt-1">
                    <SelectValue placeholder="Select book" />
                  </SelectTrigger>
                  <SelectContent>
                    {bookOptions.map((b) => (
                      <SelectItem key={b} value={b}>
                        {b}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            <div className="text-xs">
              <div className="text-muted-foreground mb-1">Status</div>
              <div>{statusLabel(selectedBookEntry)}</div>
            </div>
          </div>
        )}

        {step === "chapters" && (
          <div className="space-y-3">
            {chaptersLoading && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Loading chapters…
              </div>
            )}

            {!chaptersLoading && chapters.length > 0 && (
              <>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">
                    {selectedKeys.size} of {chapters.length} selected
                  </span>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={selectAllChapters}
                      className="text-primary hover:text-primary"
                    >
                      Select all
                    </button>
                    <button
                      type="button"
                      onClick={deselectAllChapters}
                      className="text-muted-foreground hover:text-foreground"
                    >
                      Clear
                    </button>
                  </div>
                </div>

                <div className="max-h-72 overflow-y-auto rounded-md border border-border divide-y divide-border">
                  {chapters.map((c) => {
                    const checked = selectedKeys.has(c.s3_key);
                    return (
                      <label
                        key={c.s3_key}
                        className="flex items-center gap-2 px-2 py-1.5 text-xs hover:bg-muted/40 cursor-pointer"
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleChapter(c.s3_key)}
                          className="h-3.5 w-3.5 accent-primary"
                          disabled={isWorking}
                        />
                        <span className="flex-1 truncate">{c.label}</span>
                        {c.status === "ready" && (
                          <CheckCircle2 className="h-3.5 w-3.5 text-green-500 flex-shrink-0" />
                        )}
                        {c.status === "error" && (
                          <AlertCircle className="h-3.5 w-3.5 text-red-500 flex-shrink-0" />
                        )}
                        {(c.status === "processing" ||
                          c.status === "pending") && (
                          <Loader2 className="h-3.5 w-3.5 animate-spin text-primary flex-shrink-0" />
                        )}
                      </label>
                    );
                  })}
                </div>
              </>
            )}
          </div>
        )}

        <DialogFooter className="gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => onOpenChange(false)}
            disabled={isWorking}
          >
            Cancel
          </Button>
          {step === "select" ? (
            <Button
              type="button"
              size="sm"
              onClick={handleNextToChapters}
              disabled={
                !grade ||
                !subject ||
                !book ||
                isWorking ||
                catalog?.enabled === false
              }
            >
              Choose chapters
            </Button>
          ) : (
            <Button
              type="button"
              size="sm"
              onClick={handleConfirm}
              disabled={
                !grade ||
                !subject ||
                !book ||
                isWorking ||
                catalog?.enabled === false ||
                chapters.length === 0 ||
                selectedKeys.size === 0
              }
            >
              {isWorking ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />
                  Applying…
                </>
              ) : (
                `Apply ${selectedKeys.size} chapter${selectedKeys.size === 1 ? "" : "s"}`
              )}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
