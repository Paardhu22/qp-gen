"use client";

import { GeneratorForm } from "@/components/generator-form";
import { TiptapEditor } from "@/components/tiptap-editor";
import { useEditorStore } from "@/store/editor-store";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useState, useEffect, useRef, useCallback } from "react";
import {
  fetchPaper,
  fetchProjects,
  savePaper,
  updatePaper,
} from "@/lib/api-client";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useSearchParams, useRouter } from "next/navigation";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";

export default function EditorPage() {
  const router = useRouter();
  const saveModalOpen = useEditorStore((state) => state.saveModalOpen);
  const setSaveModalOpen = useEditorStore((state) => state.setSaveModalOpen);
  const questionsToSave = useEditorStore((state) => state.questionsToSave);
  const editorContent = useEditorStore((state) => state.editorContent);

  const [paperTitle, setPaperTitle] = useState("");
  const [projectName, setProjectName] = useState("");
  const [selectedProjectId, setSelectedProjectId] = useState<string>("new");
  const [projects, setProjects] = useState<any[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [paperContent, setPaperContent] = useState<string | undefined>(
    undefined,
  );
  const [loadedPaperTitle, setLoadedPaperTitle] = useState<string | null>(null);
  const [paperLoading, setPaperLoading] = useState(false);
  const [paperError, setPaperError] = useState<string | null>(null);
  const [currentPaperId, setCurrentPaperId] = useState<string | null>(null);

  // Resizable sidebar
  const SIDEBAR_MIN = 260;
  const SIDEBAR_MAX = 600;
  const SIDEBAR_DEFAULT = 360;
  const STORAGE_KEY = "editor-sidebar-width";

  const [sidebarWidth, setSidebarWidth] = useState<number>(() => {
    if (typeof window === "undefined") return SIDEBAR_DEFAULT;
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      const n = parseInt(saved, 10);
      if (!isNaN(n) && n >= SIDEBAR_MIN && n <= SIDEBAR_MAX) return n;
    }
    return SIDEBAR_DEFAULT;
  });

  const isDragging = useRef(false);
  const dragStartX = useRef(0);
  const dragStartWidth = useRef(0);

  const onDragStart = useCallback(
    (e: React.MouseEvent) => {
      isDragging.current = true;
      dragStartX.current = e.clientX;
      dragStartWidth.current = sidebarWidth;
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
    },
    [sidebarWidth],
  );

  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!isDragging.current) return;
      const delta = e.clientX - dragStartX.current;
      const next = Math.min(
        SIDEBAR_MAX,
        Math.max(SIDEBAR_MIN, dragStartWidth.current + delta),
      );
      setSidebarWidth(next);
    };
    const onMouseUp = () => {
      if (!isDragging.current) return;
      isDragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      setSidebarWidth((prev) => {
        localStorage.setItem(STORAGE_KEY, String(prev));
        return prev;
      });
    };
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, []);

  const searchParams = useSearchParams();
  const paperId = searchParams.get("paperId");

  // Pre-fill paper title when modal opens while editing a saved paper
  useEffect(() => {
    let active = true;

    if (saveModalOpen) {
      setProjectsLoading(true);
      fetchProjects<any[]>()
        .then((data) => {
          if (active) setProjects(data);
        })
        .catch((error) => {
          console.error(error);
          toast.error("Failed to load workspace subdivisions.");
        })
        .finally(() => {
          if (active) setProjectsLoading(false);
        });
      if (loadedPaperTitle) {
        setPaperTitle((current) => current || loadedPaperTitle);
      }
    }

    return () => {
      active = false;
    };
  }, [saveModalOpen, loadedPaperTitle]);

  useEffect(() => {
    let active = true;

    if (!paperId) {
      setPaperContent("");
      setLoadedPaperTitle(null);
      setPaperError(null);
      setCurrentPaperId(null);
      return () => {
        active = false;
      };
    }

    setPaperLoading(true);
    setPaperError(null);
    setPaperContent(undefined);
    fetchPaper<{ id: string; title: string; content: string }>(paperId)
      .then((paper) => {
        if (!active) return;
        setPaperContent(paper.content || "");
        setLoadedPaperTitle(paper.title || "Saved Paper");
        setPaperTitle(paper.title || "");
        setCurrentPaperId(paper.id);
        setPaperError(null);
      })
      .catch((error) => {
        if (!active) return;
        console.error(error);
        setPaperError("Failed to load saved paper. Please try again.");
        setPaperContent("");
        toast.error(error?.message || "Failed to load saved paper.");
      })
      .finally(() => {
        if (active) setPaperLoading(false);
      });

    return () => {
      active = false;
    };
  }, [paperId]);

  const handleSave = async () => {
    if (!paperTitle.trim()) {
      toast.error("Please enter a title for the paper");
      return;
    }

    const finalProjectName =
      selectedProjectId === "new"
        ? projectName
        : projects.find((p) => p.id === selectedProjectId)?.name;

    if (!finalProjectName?.trim()) {
      toast.error("Please enter or select a workspace subdivision");
      return;
    }

    setIsSaving(true);
    try {
      const payload = {
        title: paperTitle.trim(),
        projectName: finalProjectName,
        content: editorContent,
        questions: questionsToSave,
      };

      let result: { paperId: string };

      if (currentPaperId) {
        // Update existing paper
        result = await updatePaper<{ paperId: string }>(
          currentPaperId,
          payload,
        );
      } else {
        // Create new paper
        result = await savePaper<{ paperId: string }>(payload);
        // Navigate to the URL with the new paperId so refreshing keeps the paper loaded
        router.replace(`/editor?paperId=${result.paperId}`);
        setCurrentPaperId(result.paperId);
      }

      setLoadedPaperTitle(paperTitle.trim());
      setSaveModalOpen(false);
      setProjectName("");
      setSelectedProjectId("new");
      toast.success(`Paper "${paperTitle.trim()}" saved successfully!`);
    } catch (error: any) {
      console.error(error);
      toast.error(
        error?.message ||
          "Failed to save paper. Make sure you are logged in and try again.",
      );
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="flex h-[calc(100vh-4.5rem)] w-full overflow-hidden bg-white dark:bg-zinc-950">
      {/* Left Panel: Generator Form */}
      <div
        className="flex-shrink-0 bg-white dark:bg-zinc-950 flex flex-col h-full overflow-hidden"
        style={{ width: sidebarWidth }}
      >
        <GeneratorForm />
      </div>

      {/* Drag handle */}
      <div
        onMouseDown={onDragStart}
        className="flex-shrink-0 w-px h-full cursor-col-resize group relative z-20 bg-zinc-200 dark:bg-zinc-800 hover:bg-indigo-500 transition-colors"
        title="Drag to resize"
      >
        {/* Large invisible hit area for better UX */}
        <div className="absolute inset-y-0 -left-2 -right-2 z-0" />

        {/* Grabber Handle (Visual) */}
        <div className="z-10 w-1.5 h-12 absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 group-hover:border-indigo-500 group-hover:bg-indigo-600 transition-all flex flex-col items-center justify-center gap-1 shadow-sm pointer-events-none">
          <div className="w-0.5 h-0.5 rounded-full bg-zinc-300 dark:bg-zinc-700 group-hover:bg-indigo-200" />
          <div className="w-0.5 h-0.5 rounded-full bg-zinc-300 dark:bg-zinc-700 group-hover:bg-indigo-200" />
          <div className="w-0.5 h-0.5 rounded-full bg-zinc-300 dark:bg-zinc-700 group-hover:bg-indigo-200" />
        </div>
      </div>

      {/* Right Panel: Tiptap Editor */}
      <div className="flex-1 min-w-0 bg-zinc-100 dark:bg-zinc-900 h-full flex flex-col overflow-hidden">
        <div className="h-10 min-h-10 px-4 flex items-center border-b border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-950 text-[10px] uppercase tracking-wider font-medium text-zinc-500 flex-shrink-0">
          {paperLoading ? (
            <span className="inline-flex items-center gap-2">
              <Loader2 className="h-3 w-3 animate-spin" />
              Loading saved paper...
            </span>
          ) : paperError ? (
            <span className="text-red-400">{paperError}</span>
          ) : loadedPaperTitle ? (
            <>
              <span className="text-zinc-400 mr-2">Editing:</span>
              <span className="text-zinc-800 dark:text-zinc-200">
                {loadedPaperTitle}
              </span>
            </>
          ) : (
            "New Document"
          )}
        </div>
        <TiptapEditor initialContent={paperContent} />
      </div>

      <Dialog
        open={saveModalOpen}
        onOpenChange={(open) => {
          if (!isSaving) setSaveModalOpen(open);
        }}
      >
        <DialogContent className="bg-popover border-border text-popover-foreground sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>Save Paper</DialogTitle>
            <DialogDescription className="text-muted-foreground">
              {currentPaperId
                ? "Update your saved paper and its questions."
                : `Save this paper with ${questionsToSave.length} question${questionsToSave.length !== 1 ? "s" : ""} to a workspace subdivision.`}
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="space-y-4">
              {/* Paper title */}
              <div className="flex flex-col gap-2">
                <Label htmlFor="paperTitle">
                  Paper Title <span className="text-red-400">*</span>
                </Label>
                <Input
                  id="paperTitle"
                  placeholder="e.g. French Revolution Test — May 2026"
                  value={paperTitle}
                  disabled={isSaving}
                  onChange={(e) => setPaperTitle(e.target.value)}
                />
              </div>

              {/* Workspace subdivision */}
              <div className="flex flex-col gap-2">
                <Label className="text-zinc-300">Workspace Subdivision</Label>
                <Select
                  value={selectedProjectId}
                  onValueChange={(v) => setSelectedProjectId(v as string)}
                  disabled={isSaving || projectsLoading}
                >
                  <SelectTrigger>
                    <SelectValue
                      placeholder={
                        projectsLoading
                          ? "Loading subdivisions..."
                          : "Choose existing or create new"
                      }
                    />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="new">
                      + Create New Subdivision
                    </SelectItem>
                    {projects.map((p) => (
                      <SelectItem key={p.id} value={p.id}>
                        {p.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {selectedProjectId === "new" && (
                <div className="flex flex-col gap-2 animate-in fade-in slide-in-from-top-2 duration-200">
                  <Label htmlFor="projectName">
                    New Subdivision Name
                  </Label>
                  <Input
                    id="projectName"
                    placeholder="e.g. Midterm Exams 2026"
                    value={projectName}
                    disabled={isSaving}
                    onChange={(e) => setProjectName(e.target.value)}
                  />
                </div>
              )}
            </div>
          </div>
          <DialogFooter>
            <Button
              disabled={isSaving}
              onClick={handleSave}
              className="bg-indigo-600 hover:bg-indigo-700 text-white w-full gap-2"
            >
              {isSaving && <Loader2 className="h-4 w-4 animate-spin" />}
              {isSaving ? "Saving..." : currentPaperId ? "Update Paper" : "Save Paper"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
