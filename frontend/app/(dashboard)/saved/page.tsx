"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  fetchJson,
  fetchPapers,
  fetchProjectsWithQuestions,
  deleteQuestion,
  deletePaper,
} from "@/lib/api-client";
import { Trash2, FileText } from "lucide-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { useEditorStore } from "@/store/editor-store";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

type Question = {
  id: string;
  content: string;
  answer?: string;
  options?: string[];
  type: string;
  marks: number;
};

type Project = {
  id: string;
  name: string;
  questions: Question[];
};

type SavedQuestion = Question & {
  projectId: string;
  projectName: string;
};

type Paper = {
  id: string;
  title: string;
  projectName?: string;
  created_at?: string;
  updated_at?: string;
};

const formatDate = (value?: string) => {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString();
};

export default function SavedQuestionsPage() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [isLoadingQuestions, setIsLoadingQuestions] = useState(true);
  const [isLoadingPapers, setIsLoadingPapers] = useState(true);
  const [questionSearch, setQuestionSearch] = useState("");
  const [paperSearch, setPaperSearch] = useState("");
  const [selectedQuestionIds, setSelectedQuestionIds] = useState<Set<string>>(
    new Set(),
  );
  const [selectedPaperId, setSelectedPaperId] = useState<string | null>(null);
  const [deletingIds, setDeletingIds] = useState<Set<string>>(new Set());
  const [isClearingQuestions, setIsClearingQuestions] = useState(false);
  const [isClearingPapers, setIsClearingPapers] = useState(false);
  const hasFetchedQuestions = useRef(false);

  useEffect(() => {
    if (hasFetchedQuestions.current) return;
    hasFetchedQuestions.current = true;

    fetchProjectsWithQuestions<Project[]>()
      .then(setProjects)
      .catch(console.error)
      .finally(() => setIsLoadingQuestions(false));
  }, []);

  useEffect(() => {
    fetchPapers<Paper[]>()
      .then(setPapers)
      .catch(console.error)
      .finally(() => setIsLoadingPapers(false));
  }, []);

  const allQuestions = useMemo<SavedQuestion[]>(
    () =>
      projects.flatMap((project) =>
        project.questions.map((q) => ({
          ...q,
          projectId: project.id,
          projectName: project.name,
        })),
      ),
    [projects],
  );

  const filteredQuestions = useMemo(() => {
    const term = questionSearch.trim().toLowerCase();
    if (!term) return allQuestions;
    return allQuestions.filter((q) => {
      return (
        q.content.toLowerCase().includes(term) ||
        q.projectName.toLowerCase().includes(term) ||
        q.type.toLowerCase().includes(term)
      );
    });
  }, [allQuestions, questionSearch]);

  const filteredPapers = useMemo(() => {
    const term = paperSearch.trim().toLowerCase();
    if (!term) return papers;
    return papers.filter((paper) => {
      return (
        paper.title.toLowerCase().includes(term) ||
        (paper.projectName || "").toLowerCase().includes(term)
      );
    });
  }, [papers, paperSearch]);

  const toggleQuestionSelection = (questionId: string) => {
    setSelectedQuestionIds((prev) => {
      const next = new Set(prev);
      if (next.has(questionId)) {
        next.delete(questionId);
      } else {
        next.add(questionId);
      }
      return next;
    });
  };

  const deleteQuestionById = async (questionId: string) => {
    setDeletingIds((prev) => new Set(prev).add(questionId));
    try {
      await deleteQuestion(questionId);
      // Optimistic update: remove from projects state
      setProjects((prev) =>
        prev.map((project) => ({
          ...project,
          questions: project.questions.filter((q) => q.id !== questionId),
        })),
      );
      toast.success("Question deleted.");
    } catch {
      toast.error("Failed to delete question. Please try again.");
    } finally {
      setDeletingIds((prev) => {
        const next = new Set(prev);
        next.delete(questionId);
        return next;
      });
    }
  };

  const handleDeleteQuestion = (questionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    toast.warning("Delete this question?", {
      description: "This cannot be undone.",
      action: {
        label: "Delete",
        onClick: () => void deleteQuestionById(questionId),
      },
    });
  };

  const deletePaperById = async (paperId: string) => {
    setDeletingIds((prev) => new Set(prev).add(paperId));
    try {
      await deletePaper(paperId);
      // Optimistic update: remove from papers state
      setPapers((prev) => prev.filter((p) => p.id !== paperId));
      toast.success("Paper deleted.");
    } catch {
      toast.error("Failed to delete paper. Please try again.");
    } finally {
      setDeletingIds((prev) => {
        const next = new Set(prev);
        next.delete(paperId);
        return next;
      });
    }
  };

  const handleDeletePaper = (paperId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    toast.warning("Delete this paper?", {
      description: "This cannot be undone.",
      action: {
        label: "Delete",
        onClick: () => void deletePaperById(paperId),
      },
    });
  };

  const handlePaperOpen = (paper: Paper) => {
    setSelectedPaperId(paper.id);
    router.push(`/editor?paperId=${paper.id}`);
  };

  const handleClearAllQuestions = async () => {
    setIsClearingQuestions(true);
    try {
      await fetchJson("/api/projects/questions/clear", { method: "DELETE" });
      setProjects([]);
      setSelectedQuestionIds(new Set());
      toast.success("All saved questions cleared.");
    } catch {
      toast.error("Failed to clear questions. Please try again.");
    } finally {
      setIsClearingQuestions(false);
    }
  };

  const handleClearAllPapers = async () => {
    setIsClearingPapers(true);
    try {
      await fetchJson("/api/projects/papers/clear", { method: "DELETE" });
      setPapers([]);
      setSelectedPaperId(null);
      toast.success("All saved papers cleared.");
    } catch {
      toast.error("Failed to clear papers. Please try again.");
    } finally {
      setIsClearingPapers(false);
    }
  };

  const handleInsertSelectedQuestions = () => {
    const selectedList = allQuestions.filter((q) =>
      selectedQuestionIds.has(q.id),
    );
    if (selectedList.length === 0) return;

    const questionsToAppend = selectedList.map((q) => ({
      content: q.content,
      type: q.type,
      options: q.options || [],
      answer: q.answer || "",
      marks: q.marks,
    }));

    useEditorStore.getState().appendQuestions(questionsToAppend);
    toast.success(`Inserted ${selectedList.length} questions into the editor.`);
    setSelectedQuestionIds(new Set());
  };

  return (
    <div className="p-8 space-y-8 bg-background min-h-full">
      <div>
        <h2 className="text-3xl font-bold tracking-tight text-foreground">
          Saved Items
        </h2>
        <p className="text-muted-foreground mt-2">
          View and manage your saved exam questions and completed papers.
        </p>
      </div>

      <div className="grid gap-8 grid-cols-1 lg:grid-cols-3">
        {/* Questions Section */}
        <div className="lg:col-span-2 space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <h3 className="text-xl font-semibold text-foreground flex items-center gap-2">
                Saved Questions
                {!isLoadingQuestions && (
                  <span className="inline-flex items-center justify-center h-5 min-w-5 px-1.5 rounded-full bg-indigo-100 text-indigo-600 text-[11px] font-bold dark:bg-indigo-950 dark:text-indigo-400">
                    {allQuestions.length}
                  </span>
                )}
              </h3>
              {!isLoadingQuestions && allQuestions.length > 0 && (
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <button
                      type="button"
                      disabled={isClearingQuestions}
                      className="flex items-center gap-1.5 text-xs text-destructive/70 hover:text-destructive border border-destructive/30 hover:border-destructive/60 hover:bg-destructive/5 px-2.5 py-1 rounded-lg transition-colors"
                    >
                      <Trash2 className="h-3 w-3" />
                      Clear All
                    </button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>
                        Clear all saved questions?
                      </AlertDialogTitle>
                      <AlertDialogDescription>
                        This will permanently delete all {allQuestions.length}{" "}
                        saved question{allQuestions.length !== 1 ? "s" : ""}{" "}
                        across every workspace. This action cannot be undone.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Cancel</AlertDialogCancel>
                      <AlertDialogAction
                        onClick={handleClearAllQuestions}
                        className="bg-destructive hover:bg-destructive/90 text-white"
                      >
                        Yes, delete all
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              )}
              {selectedQuestionIds.size > 0 && (
                <button
                  type="button"
                  onClick={handleInsertSelectedQuestions}
                  className="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs px-3 py-1.5 rounded-lg flex items-center gap-1.5 shadow-sm transition-all duration-200 cursor-pointer"
                >
                  <FileText className="h-3.5 w-3.5" />
                  Insert Selected ({selectedQuestionIds.size}) into Editor
                </button>
              )}
            </div>
            <div className="w-full sm:w-64">
              <Input
                placeholder="Search questions..."
                value={questionSearch}
                onChange={(e) => setQuestionSearch(e.target.value)}
                className="h-9 bg-background border-border text-foreground"
              />
            </div>
          </div>

          {isLoadingQuestions ? (
            <div className="text-muted-foreground text-center py-12 border border-dashed border-border rounded-lg">
              Loading questions...
            </div>
          ) : filteredQuestions.length === 0 ? (
            <div className="text-muted-foreground text-center py-12 border border-dashed border-border rounded-lg">
              {questionSearch
                ? "No questions match your search."
                : "No saved questions found."}
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {filteredQuestions.map((q) => (
                <Card
                  key={q.id}
                  className={cn(
                    "bg-card border-border flex flex-col h-full hover:shadow-md transition-shadow",
                    selectedQuestionIds.has(q.id) &&
                      "border-primary/60 shadow-sm",
                  )}
                >
                  <CardHeader className="pb-3">
                    <div className="flex justify-between items-start gap-2 mb-1">
                      <Badge
                        variant="outline"
                        className="text-[10px] uppercase tracking-wider border-primary/50 text-primary bg-primary/10"
                      >
                        {q.type}
                      </Badge>
                      <div className="flex items-center gap-1.5">
                        <Badge
                          variant="secondary"
                          className="text-[10px] font-bold"
                        >
                          {q.marks} Marks
                        </Badge>
                        <button
                          type="button"
                          onClick={(e) => handleDeleteQuestion(q.id, e)}
                          disabled={deletingIds.has(q.id)}
                          title="Delete question"
                          className="p-1 rounded text-muted-foreground hover:text-red-500 hover:bg-red-500/10 transition-colors disabled:opacity-40"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                    <p className="text-sm text-card-foreground">{q.content}</p>
                    <div className="mt-2 text-[11px] text-zinc-500">
                      {q.projectName}
                    </div>
                  </CardHeader>
                  <CardContent className="mt-auto">
                    <button
                      type="button"
                      onClick={() => toggleQuestionSelection(q.id)}
                      className={cn(
                        "w-full rounded-md border px-3 py-2 text-xs font-semibold transition",
                        selectedQuestionIds.has(q.id)
                          ? "border-primary/60 bg-primary/10 text-primary"
                          : "border-border bg-muted/30 text-muted-foreground hover:border-primary/40",
                      )}
                    >
                      {selectedQuestionIds.has(q.id) ? "Selected" : "Select"}
                    </button>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>

        {/* Papers Section */}
        <div className="space-y-6">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-xl font-semibold text-foreground flex items-center gap-2">
              Saved Papers
              {!isLoadingPapers && (
                <span className="inline-flex items-center justify-center h-5 min-w-5 px-1.5 rounded-full bg-indigo-100 text-indigo-600 text-[11px] font-bold dark:bg-indigo-950 dark:text-indigo-400">
                  {papers.length}
                </span>
              )}
            </h3>
            {!isLoadingPapers && papers.length > 0 && (
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <button
                    type="button"
                    disabled={isClearingPapers}
                    className="flex items-center gap-1.5 text-xs text-destructive/70 hover:text-destructive border border-destructive/30 hover:border-destructive/60 hover:bg-destructive/5 px-2.5 py-1 rounded-lg transition-colors"
                  >
                    <Trash2 className="h-3 w-3" />
                    Clear All
                  </button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Clear all saved papers?</AlertDialogTitle>
                    <AlertDialogDescription>
                      This will permanently delete all {papers.length} saved
                      paper{papers.length !== 1 ? "s" : ""}. This action cannot
                      be undone.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction
                      onClick={handleClearAllPapers}
                      className="bg-destructive hover:bg-destructive/90 text-white"
                    >
                      Yes, delete all
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            )}
          </div>

          <Card className="bg-card border-border flex flex-col">
            <CardHeader className="pb-3">
              <CardTitle className="text-lg text-foreground">
                Saved Papers
              </CardTitle>
              <CardDescription className="text-muted-foreground">
                Continue editing your previously saved papers.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Input
                value={paperSearch}
                onChange={(e) => setPaperSearch(e.target.value)}
                placeholder="Search papers or workspace..."
                className="h-9 bg-background border-border"
              />
              {isLoadingPapers ? (
                <div className="text-muted-foreground text-center py-10 border border-dashed border-border rounded-lg">
                  Loading papers...
                </div>
              ) : filteredPapers.length === 0 ? (
                <div className="text-muted-foreground text-center py-10 border border-dashed border-border rounded-lg">
                  No saved papers found.
                </div>
              ) : (
                <div className="space-y-3 max-h-[600px] overflow-y-auto custom-scrollbar pr-2">
                  {filteredPapers.map((paper) => (
                    // Must be a div, not a button — the delete button inside
                    // would create an illegal nested <button>.<button> in HTML.
                    <div
                      key={paper.id}
                      role="button"
                      tabIndex={0}
                      onClick={() => handlePaperOpen(paper)}
                      onKeyDown={(e) =>
                        e.key === "Enter" && handlePaperOpen(paper)
                      }
                      className={cn(
                        "w-full text-left p-4 rounded-xl border transition-all duration-200 cursor-pointer",
                        selectedPaperId === paper.id
                          ? "border-primary bg-primary/5 shadow-sm"
                          : "border-border bg-muted/30 hover:border-primary/50 hover:bg-muted/50",
                      )}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="text-sm font-semibold text-foreground truncate">
                            {paper.title}
                          </div>
                          <div className="text-[11px] text-muted-foreground mt-1 flex items-center gap-2">
                            <span className="inline-block w-1 h-1 rounded-full bg-primary/40" />
                            {paper.projectName || "Default Workspace"}
                          </div>
                        </div>
                        <div className="flex items-center gap-1.5 flex-shrink-0">
                          <div className="text-[10px] text-muted-foreground whitespace-nowrap bg-background px-2 py-0.5 rounded border border-border">
                            {formatDate(paper.updated_at || paper.created_at)}
                          </div>
                          <button
                            type="button"
                            onClick={(e) => handleDeletePaper(paper.id, e)}
                            disabled={deletingIds.has(paper.id)}
                            title="Delete paper"
                            className="p-1 rounded text-muted-foreground hover:text-red-500 hover:bg-red-500/10 transition-colors disabled:opacity-40"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
