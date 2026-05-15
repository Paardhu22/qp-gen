"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  fetchPapers,
  fetchProjectsWithQuestions,
  deleteQuestion,
  deletePaper,
} from "@/lib/api-client";
import { Trash2 } from "lucide-react";
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

  const handleDeleteQuestion = async (
    questionId: string,
    e: React.MouseEvent,
  ) => {
    e.stopPropagation();
    if (!window.confirm("Delete this question? This cannot be undone.")) return;
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
    } catch {
      alert("Failed to delete question. Please try again.");
    } finally {
      setDeletingIds((prev) => {
        const next = new Set(prev);
        next.delete(questionId);
        return next;
      });
    }
  };

  const handleDeletePaper = async (paperId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm("Delete this paper? This cannot be undone.")) return;
    setDeletingIds((prev) => new Set(prev).add(paperId));
    try {
      await deletePaper(paperId);
      // Optimistic update: remove from papers state
      setPapers((prev) => prev.filter((p) => p.id !== paperId));
    } catch {
      alert("Failed to delete paper. Please try again.");
    } finally {
      setDeletingIds((prev) => {
        const next = new Set(prev);
        next.delete(paperId);
        return next;
      });
    }
  };

  const handlePaperOpen = (paper: Paper) => {
    setSelectedPaperId(paper.id);
    router.push(`/editor?paperId=${paper.id}`);
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
          <div className="flex items-center justify-between">
            <h3 className="text-xl font-semibold text-foreground">
              Saved Questions
            </h3>
            <div className="w-64">
              <Input
                placeholder="Search questions..."
                value={questionSearch}
                onChange={(e) => setQuestionSearch(e.target.value)}
                className="h-9 bg-background border-border"
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
                    <p className="text-sm text-zinc-200">{q.content}</p>
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
          <h3 className="text-xl font-semibold text-foreground">
            Saved Papers
          </h3>

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
