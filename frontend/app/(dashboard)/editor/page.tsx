"use client";

import { GeneratorForm } from "@/components/generator-form";
import { TiptapEditor } from "@/components/tiptap-editor";
import { useEditorStore } from "@/store/editor-store";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useState, useEffect } from "react";
import { fetchProjects, saveQuestions } from "@/lib/api-client";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export default function EditorPage() {
  const { saveModalOpen, setSaveModalOpen, questionsToSave } = useEditorStore();
  const [projectName, setProjectName] = useState("");
  const [selectedProjectId, setSelectedProjectId] = useState<string>("new");
  const [projects, setProjects] = useState<any[]>([]);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (saveModalOpen) {
      fetchProjects<any[]>().then(setProjects).catch(console.error);
    }
  }, [saveModalOpen]);

  const handleSave = async () => {
    const finalProjectName = selectedProjectId === "new" ? projectName : projects.find(p => p.id === selectedProjectId)?.name;
    
    if (!finalProjectName?.trim()) return alert("Please enter or select a workspace subdivision");
    
    setIsSaving(true);
    try {
      await saveQuestions({
        projectName: finalProjectName,
        questions: questionsToSave,
      });
      alert("Questions saved to workspace successfully!");
      setSaveModalOpen(false);
      setProjectName("");
      setSelectedProjectId("new");
    } catch (error) {
      console.error(error);
      alert("Failed to save questions. Make sure you are logged in.");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="flex h-[calc(100vh-4.5rem)] w-full overflow-hidden bg-zinc-950">
      {/* Left Panel: Generator Form */}
      <div className="w-[350px] lg:w-[400px] flex-shrink-0 border-r border-zinc-800 bg-zinc-950 flex flex-col h-full overflow-hidden">
        <GeneratorForm />
      </div>
      
      {/* Right Panel: Tiptap Editor */}
      <div className="flex-1 min-w-0 bg-zinc-900 h-full flex flex-col overflow-hidden">
        <TiptapEditor />
      </div>

      <Dialog open={saveModalOpen} onOpenChange={setSaveModalOpen}>
        <DialogContent className="bg-zinc-900 border-zinc-800 text-zinc-100 sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>Save to Workspace</DialogTitle>
            <DialogDescription className="text-zinc-400">
              Save {questionsToSave.length} generated questions to a workspace subdivision.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="space-y-4">
              <div className="flex flex-col gap-2">
                <Label className="text-zinc-300">Select Subdivision</Label>
                <Select value={selectedProjectId} onValueChange={(v) => setSelectedProjectId(v as string)}>
                  <SelectTrigger className="bg-zinc-800 border-zinc-700">
                    <SelectValue placeholder="Choose existing or create new" />
                  </SelectTrigger>
                  <SelectContent className="bg-zinc-800 border-zinc-700 text-zinc-100">
                    <SelectItem value="new">+ Create New Subdivision</SelectItem>
                    {projects.map((p) => (
                      <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
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
            <Button disabled={isSaving} onClick={handleSave} className="bg-indigo-600 hover:bg-indigo-700 text-white w-full">
              {isSaving ? "Saving..." : "Confirm Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
