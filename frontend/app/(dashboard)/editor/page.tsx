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

export default function EditorPage() {
  const router = useRouter();
  const { saveModalOpen, setSaveModalOpen, questionsToSave, editorContent } =
    useEditorStore();

  const [paperTitle, setPaperTitle] = useState("");
  const [projectName, setProjectName] = useState("");
  const [selectedProjectId, setSelectedProjectId] = useState<string>("new");
  const [projects, setProjects] = useState<any[]>([]);
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
    if (saveModalOpen) {
      fetchProjects<any[]>().then(setProjects).catch(console.error);
      if (loadedPaperTitle && !paperTitle) {
        setPaperTitle(loadedPaperTitle);
      }
    }
  }, [saveModalOpen]);

  useEffect(() => {
    if (!paperId) {
      setPaperContent("");
      setLoadedPaperTitle(null);
      setPaperError(null);
      setCurrentPaperId(null);
      return;
    }

    setPaperLoading(true);
    fetchPaper<{ id: string; title: string; content: string }>(paperId)
      .then((paper) => {
        setPaperContent(paper.content || "");
        setLoadedPaperTitle(paper.title || "Saved Paper");
        setPaperTitle(paper.title || "");
        setCurrentPaperId(paper.id);
        setPaperError(null);
      })
      .catch((error) => {
        console.error(error);
        setPaperError("Failed to load saved paper. Please try again.");
        setPaperContent("");
      })
      .finally(() => setPaperLoading(false));
  }, [paperId]);

  const handleSave = async () => {
    if (!paperTitle.trim()) return alert("Please enter a title for the paper");

    const finalProjectName =
      selectedProjectId === "new"
        ? projectName
        : projects.find((p) => p.id === selectedProjectId)?.name;

    if (!finalProjectName?.trim())
      return alert("Please enter or select a workspace subdivision");

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
      alert(`Paper "${paperTitle.trim()}" saved successfully!`);
    } catch (error) {
      console.error(error);
      alert("Failed to save paper. Make sure you are logged in.");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="flex h-[calc(100vh-4.5rem)] w-full overflow-hidden bg-zinc-950">
      {/* Left Panel: Generator Form */}
      <div
        className="flex-shrink-0 bg-zinc-950 flex flex-col h-full overflow-hidden border-r border-zinc-800"
        style={{ width: sidebarWidth }}
      >
        <GeneratorForm />
      </div>

      {/* Drag handle */}
      <div
        onMouseDown={onDragStart}
        className="flex-shrink-0 w-1.5 h-full cursor-col-resize bg-zinc-800 hover:bg-indigo-500 active:bg-indigo-400 transition-colors group relative z-10"
        title="Drag to resize"
      >
        {/* Grip dots */}
        <div className="absolute inset-y-0 left-1/2 -translate-x-1/2 flex flex-col items-center justify-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <div className="w-0.5 h-0.5 rounded-full bg-white" />
          <div className="w-0.5 h-0.5 rounded-full bg-white" />
          <div className="w-0.5 h-0.5 rounded-full bg-white" />
          <div className="w-0.5 h-0.5 rounded-full bg-white" />
          <div className="w-0.5 h-0.5 rounded-full bg-white" />
        </div>
      </div>

      {/* Right Panel: Tiptap Editor */}
      <div className="flex-1 min-w-0 bg-zinc-900 h-full flex flex-col overflow-hidden">
        {currentPaperId && (
          <div className="px-4 py-2 border-b border-zinc-800 bg-zinc-950 text-xs text-zinc-300">
            {paperLoading && "Loading saved paper..."}
            {!paperLoading && paperError && (
              <span className="text-red-400">{paperError}</span>
            )}
            {!paperLoading &&
              !paperError &&
              loadedPaperTitle &&
              `Editing: ${loadedPaperTitle}`}
          </div>
        )}
        <TiptapEditor initialContent={paperContent} />
      </div>

      <Dialog open={saveModalOpen} onOpenChange={setSaveModalOpen}>
        <DialogContent className="bg-zinc-900 border-zinc-800 text-zinc-100 sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>Save Paper</DialogTitle>
            <DialogDescription className="text-zinc-400">
              {currentPaperId
                ? "Update your saved paper and its questions."
                : `Save this paper with ${questionsToSave.length} question${questionsToSave.length !== 1 ? "s" : ""} to a workspace subdivision.`}
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="space-y-4">
              {/* Paper title */}
              <div className="flex flex-col gap-2">
                <Label htmlFor="paperTitle" className="text-zinc-300">
                  Paper Title <span className="text-red-400">*</span>
                </Label>
                <Input
                  id="paperTitle"
                  placeholder="e.g. French Revolution Test — May 2026"
                  className="bg-zinc-800 border-zinc-700"
                  value={paperTitle}
                  onChange={(e) => setPaperTitle(e.target.value)}
                />
              </div>

              {/* Workspace subdivision */}
              <div className="flex flex-col gap-2">
                <Label className="text-zinc-300">Workspace Subdivision</Label>
                <Select
                  value={selectedProjectId}
                  onValueChange={(v) => setSelectedProjectId(v as string)}
                >
                  <SelectTrigger className="bg-zinc-800 border-zinc-700">
                    <SelectValue placeholder="Choose existing or create new" />
                  </SelectTrigger>
                  <SelectContent className="bg-zinc-800 border-zinc-700 text-zinc-100">
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
                  <Label htmlFor="projectName" className="text-zinc-300">
                    New Subdivision Name
                  </Label>
                  <Input
                    id="projectName"
                    placeholder="e.g. Midterm Exams 2026"
                    className="bg-zinc-800 border-zinc-700"
                    value={projectName}
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
              className="bg-indigo-600 hover:bg-indigo-700 text-white w-full"
            >
              {isSaving
                ? "Saving..."
                : currentPaperId
                  ? "Update Paper"
                  : "Save Paper"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
