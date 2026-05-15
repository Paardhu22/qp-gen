"use client";

import { useEffect, useMemo, useState } from "react";
import { fetchPapers, fetchProjectsWithQuestions } from "@/lib/api-client";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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
  const [selectedQuestionIds, setSelectedQuestionIds] = useState<Set<string>>(new Set());
  const [selectedPaperId, setSelectedPaperId] = useState<string | null>(null);

  useEffect(() => {
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
        }))
      ),
    [projects]
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

  const handlePaperOpen = (paper: Paper) => {
    setSelectedPaperId(paper.id);
    router.push(`/editor?paperId=${paper.id}`);
  };

  return (
    <div className="p-8 space-y-6 bg-zinc-950 min-h-full">
      <div>
        <h2 className="text-3xl font-bold tracking-tight text-white">Saved Workspace</h2>
        <p className="text-zinc-400 mt-2">
          Review saved questions on the left and saved papers on the right.
        </p>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card className="bg-zinc-900 border-zinc-800 flex flex-col">
          <CardHeader className="pb-3">
            <CardTitle className="text-lg text-zinc-100">Saved Questions</CardTitle>
            <CardDescription className="text-zinc-400">
              Search and select individual questions from your subdivisions.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Input
              value={questionSearch}
              onChange={(e) => setQuestionSearch(e.target.value)}
              placeholder="Search questions, project, or type..."
              className="bg-zinc-950 border-zinc-800"
            />

            {isLoadingQuestions ? (
              <div className="text-zinc-500 text-center py-10 border border-dashed border-zinc-800 rounded-lg">
                Loading saved questions...
              </div>
            ) : filteredQuestions.length === 0 ? (
              <div className="text-zinc-500 text-center py-10 border border-dashed border-zinc-800 rounded-lg">
                No saved questions found.
              </div>
            ) : (
              <div className="space-y-3 max-h-[560px] overflow-y-auto custom-scrollbar pr-2">
                {filteredQuestions.map((q, idx) => (
                  <button
                    key={q.id}
                    onClick={() => toggleQuestionSelection(q.id)}
                    className={cn(
                      "w-full text-left p-3 rounded-md border transition",
                      selectedQuestionIds.has(q.id)
                        ? "border-indigo-500 bg-indigo-500/10"
                        : "border-zinc-800 bg-zinc-950 hover:border-indigo-900/60"
                    )}
                  >
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <div className="text-xs text-zinc-500">Q{idx + 1}</div>
                      <Badge
                        variant="outline"
                        className="text-xs border-indigo-900/50 text-indigo-400 bg-indigo-950/20"
                      >
                        {q.type} - {q.marks}m
                      </Badge>
                    </div>
                    <p className="text-sm text-zinc-200">{q.content}</p>
                    <div className="mt-2 text-[11px] text-zinc-500">{q.projectName}</div>
                  </button>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="bg-zinc-900 border-zinc-800 flex flex-col">
          <CardHeader className="pb-3">
            <CardTitle className="text-lg text-zinc-100">Saved Papers</CardTitle>
            <CardDescription className="text-zinc-400">
              Open a saved paper to continue editing in the paper editor.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Input
              value={paperSearch}
              onChange={(e) => setPaperSearch(e.target.value)}
              placeholder="Search papers or workspace..."
              className="bg-zinc-950 border-zinc-800"
            />
            {isLoadingPapers ? (
              <div className="text-zinc-500 text-center py-10 border border-dashed border-zinc-800 rounded-lg">
                Loading saved papers...
              </div>
            ) : filteredPapers.length === 0 ? (
              <div className="text-zinc-500 text-center py-10 border border-dashed border-zinc-800 rounded-lg">
                No saved papers found.
              </div>
            ) : (
              <div className="space-y-3 max-h-[560px] overflow-y-auto custom-scrollbar pr-2">
                {filteredPapers.map((paper) => (
                  <button
                    key={paper.id}
                    onClick={() => handlePaperOpen(paper)}
                    className={cn(
                      "w-full text-left p-4 rounded-md border transition",
                      selectedPaperId === paper.id
                        ? "border-emerald-500 bg-emerald-500/10"
                        : "border-zinc-800 bg-zinc-950 hover:border-emerald-900/60"
                    )}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="text-sm font-semibold text-zinc-100">{paper.title}</div>
                        <div className="text-[11px] text-zinc-500 mt-1">
                          {paper.projectName || "Workspace"}
                        </div>
                      </div>
                      <div className="text-[11px] text-zinc-500">
                        {formatDate(paper.updated_at || paper.created_at)}
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
