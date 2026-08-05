"use client";

/**
 * Editing one saved template, end to end.
 *
 * This is the surface the Blueprint Builder never had: the Builder edits the
 * blueprint of the paper you are about to generate, and saving a template was a
 * side effect of that. Here the template itself is the subject, so a teacher can
 * fix "Friday Test" in November without generating a paper to do it.
 *
 * The save is a PATCH of only what changed, compared against the template as it
 * was loaded. That matters for more than bytes on the wire: the API leaves
 * absent keys alone, so sending the whole object would make every save a
 * blind overwrite of fields this panel may not even show.
 *
 * The pinned/instruction-driven split (see backend `services/templates.py`) is
 * editable here rather than implied. Adding slots pins a template; clearing them
 * hands it back to its prose. Both are legitimate and neither should require
 * deleting and re-saving.
 */

import * as React from "react";
import { toast } from "sonner";
import { Loader2, Trash2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SlotEditor } from "@/components/blueprint/slot-editor";
import { recomputeTotals } from "@/lib/blueprint-totals";
import {
  fetchQuestionTypeMenu,
  savePaperTemplate,
  updatePaperTemplate,
  type BlueprintSlot,
  type PaperTemplate,
  type QuestionTypeOption,
  type TemplateFolder,
} from "@/lib/api-client";

/** Mirrors the Blueprint Builder's own lists (`blueprint-modal.tsx`) — kept
 *  local rather than shared, since neither is meant to be an API contract. */
const CLASSES = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"];
const SUBJECTS = [
  "Science",
  "Social Science",
  "Mathematics",
  "English",
  "Hindi",
  "Telugu",
  "Sanskrit",
  "Computer Science",
];
const DIFFICULTIES = ["easy", "medium", "hard"];

interface Props {
  /** null starts a brand-new template instead of editing a saved one. */
  template: PaperTemplate | null;
  folders: TemplateFolder[];
  /** Where a new template lands. Ignored once `template` is set. */
  initialFolderId?: string | null;
  onClose: () => void;
  onSaved: (template: PaperTemplate) => void;
}

export function TemplateEditorPanel({
  template,
  folders,
  initialFolderId = null,
  onClose,
  onSaved,
}: Props) {
  const isCreating = template === null;

  const [name, setName] = React.useState(template?.name ?? "");
  const [instructions, setInstructions] = React.useState(
    template?.instructions ?? "",
  );
  const [folderId, setFolderId] = React.useState<string | null>(
    template ? template.folderId : initialFolderId,
  );
  const [slots, setSlots] = React.useState<BlueprintSlot[]>(
    template?.blueprint.slots ?? [],
  );
  const [questionTypes, setQuestionTypes] = React.useState<
    QuestionTypeOption[]
  >([]);
  const [isSaving, setIsSaving] = React.useState(false);

  const [subject, setSubject] = React.useState(
    template?.settings?.subject ?? SUBJECTS[0],
  );
  const [academicClass, setAcademicClass] = React.useState(
    template?.settings?.academicClass ?? "10",
  );
  const [difficulty, setDifficulty] = React.useState(
    template?.settings?.difficulty ?? "medium",
  );

  React.useEffect(() => {
    let cancelled = false;
    fetchQuestionTypeMenu(subject)
      .then((types) => {
        if (!cancelled) setQuestionTypes(types);
      })
      .catch(() => {
        // A missing menu degrades the type <select> to whatever each slot
        // already holds (SlotEditor renders an unknown value rather than
        // silently rewriting it), so this is not worth interrupting an edit.
      });
    return () => {
      cancelled = true;
    };
  }, [subject]);

  const totals = React.useMemo(() => recomputeTotals(slots), [slots]);

  const slotsChanged = React.useMemo(
    () =>
      !template ||
      JSON.stringify(slots) !== JSON.stringify(template.blueprint.slots),
    [slots, template],
  );
  const isDirty =
    isCreating ||
    name !== template.name ||
    instructions !== template.instructions ||
    folderId !== template.folderId ||
    slotsChanged;

  // The same rule the API enforces, checked here so the teacher sees it while
  // they can still fix it rather than as a rejected save.
  const isReproducible = instructions.trim().length > 0 || slots.length > 0;

  const handleSave = async () => {
    if (!name.trim()) {
      toast.error("A template needs a name.");
      return;
    }
    if (!isReproducible) {
      toast.error(
        "Give this template either instructions or at least one question slot — otherwise it cannot rebuild a paper.",
      );
      return;
    }

    setIsSaving(true);
    try {
      if (isCreating) {
        const created = await savePaperTemplate({
          name: name.trim(),
          instructions,
          folderId,
          settings: { subject, academicClass, difficulty },
          blueprint: slots.length ? { slots } : undefined,
        });
        toast.success(`Created "${created.name}"`);
        onSaved(created);
        return;
      }

      // Only what actually changed. Absent keys are left alone server-side.
      const body: Parameters<typeof updatePaperTemplate>[1] = {};
      if (name !== template.name) body.name = name.trim();
      if (instructions !== template.instructions) body.instructions = instructions;
      if (folderId !== template.folderId) body.folderId = folderId;
      if (slotsChanged) {
        body.blueprint = slots.length ? { slots } : null;
      }
      const saved = await updatePaperTemplate(template.id, body);
      toast.success(`Saved "${saved.name}"`);
      onSaved(saved);
    } catch (error: any) {
      toast.error(
        error?.message ||
          `Could not ${isCreating ? "create" : "save"} that template.`,
      );
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-stretch justify-end">
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={isDirty ? undefined : onClose}
        aria-hidden="true"
      />

      <div className="relative z-10 flex h-full w-full max-w-3xl flex-col border-l border-border bg-background shadow-2xl">
        <div className="flex shrink-0 items-center justify-between gap-3 border-b border-border px-5 py-3">
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold">
              {isCreating ? "New template" : "Edit template"}
            </h2>
            <p className="text-xs text-muted-foreground">
              {totals.totalQuestions} questions · {totals.totalMarks} marks
              {slots.length === 0 ? " · resolved from instructions" : ""}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-5 py-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="template-name">Name</Label>
              <Input
                id="template-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Friday Recap"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="template-folder">Folder</Label>
              <select
                id="template-folder"
                value={folderId ?? ""}
                onChange={(e) => setFolderId(e.target.value || null)}
                className="h-9 w-full rounded-lg border border-input bg-transparent px-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
              >
                <option value="">Unfiled</option>
                {folders.map((folder) => (
                  <option key={folder.id} value={folder.id}>
                    {folder.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {isCreating ? (
            <div className="grid gap-4 sm:grid-cols-3">
              <div className="space-y-2">
                <Label htmlFor="template-class">Class</Label>
                <select
                  id="template-class"
                  value={academicClass}
                  onChange={(e) => setAcademicClass(e.target.value)}
                  className="h-9 w-full rounded-lg border border-input bg-transparent px-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
                >
                  {CLASSES.map((c) => (
                    <option key={c} value={c}>
                      Class {c}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="template-subject">Subject</Label>
                <select
                  id="template-subject"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  className="h-9 w-full rounded-lg border border-input bg-transparent px-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
                >
                  {SUBJECTS.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="template-difficulty">Difficulty</Label>
                <select
                  id="template-difficulty"
                  value={difficulty}
                  onChange={(e) => setDifficulty(e.target.value)}
                  className="h-9 w-full rounded-lg border border-input bg-transparent px-2 text-sm capitalize shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
                >
                  {DIFFICULTIES.map((d) => (
                    <option key={d} value={d}>
                      {d}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          ) : null}

          <div className="space-y-2">
            <Label htmlFor="template-instructions">Instructions</Label>
            <textarea
              id="template-instructions"
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              rows={3}
              placeholder="20 mark photosynthesis test, mostly recall"
              className="w-full resize-y rounded-lg border border-input bg-transparent px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
            />
            <p className="text-xs leading-relaxed text-muted-foreground">
              {slots.length > 0
                ? "This template has its own question slots, so they are what gets built. The instructions are kept as a note."
                : "With no question slots saved, this prose is re-read every time the template is used — so the paper can come out differently each time."}
            </p>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Question slots</Label>
              {slots.length > 0 ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-7 gap-1.5 text-xs text-muted-foreground"
                  onClick={() => setSlots([])}
                  title="Drop the fixed structure and let the instructions decide each time"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Clear structure
                </Button>
              ) : null}
            </div>

            {isCreating || slots.length > 0 ? (
              <SlotEditor
                slots={slots}
                questionTypes={questionTypes}
                totals={totals}
                onChange={setSlots}
              />
            ) : (
              <p className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-xs leading-relaxed text-muted-foreground">
                No fixed structure. This template is rebuilt from its
                instructions each time it is used.
              </p>
            )}
          </div>
        </div>

        <div className="flex shrink-0 items-center justify-between gap-3 border-t border-border bg-muted/20 px-5 py-3">
          <p className="text-xs text-muted-foreground">
            {!isReproducible
              ? "Add instructions or a question slot to save."
              : isCreating
                ? "Ready to create"
                : isDirty
                  ? "Unsaved changes"
                  : "No changes"}
          </p>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={onClose}>
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={handleSave}
              disabled={isSaving || !isDirty || !isReproducible}
              className="gap-1.5"
            >
              {isSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
              {isCreating ? "Create" : "Save"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
