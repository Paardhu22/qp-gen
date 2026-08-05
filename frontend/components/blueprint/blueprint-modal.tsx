"use client";

/**
 * The Blueprint Builder — the one place a paper is configured.
 *
 * This replaces the 1,865-line generator sidebar and, with it, the "QP Type"
 * fork. A teacher no longer declares which *mode* they are in before they can
 * say what they want; they pick a paper, look at its questions, and change
 * whatever they like.
 *
 * ## Shape
 *
 * Three steps with a live summary that never leaves the screen:
 *
 *     ┌───────────────────────────────────────────────┐
 *     │  Create a paper                          [✕]  │
 *     ├──────────────┬────────────────────────────────┤
 *     │ ① Template   │                                │
 *     │ ② Sources    │        step content            │
 *     │ ③ Questions  │                                │
 *     ├──────────────┴────────────────────────────────┤
 *     │ 38 questions · 80 marks · 12 from bank  [Go]  │
 *     └───────────────────────────────────────────────┘
 *
 * The footer is load-bearing, not decoration. The single most common thing to
 * get wrong when editing a paper is the mark total, and a teacher should never
 * have to leave the step they are on to find out they have broken it.
 *
 * ## Steps are navigable, not sequential
 *
 * Every step is reachable at any time once a template is chosen. A wizard that
 * forces a teacher through sources to fix a typo in question 12 is a wizard
 * they will avoid, and the only genuine dependency is that step 1 produces the
 * blueprint steps 2 and 3 edit.
 */

import * as React from "react";
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  FileStack,
  Save,
  X,
} from "lucide-react";
import { toast } from "sonner";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import {
  EMPTY_BLUEPRINT,
  deletePaperTemplate,
  fetchQuestionTypeMenu,
  fetchTemplateCatalog,
  resolveTemplate,
  savePaperTemplate,
  type Blueprint,
  type BlueprintSlot,
  type BuiltinTemplate,
  type PaperTemplate,
  type QuestionTypeOption,
} from "@/lib/api-client";
import { recomputeTotals } from "@/lib/blueprint-totals";
import type { AppliedHsatSource } from "@/components/hsat-source-picker";

import { TemplatePickerGrid } from "./template-picker-grid";
import { SlotEditor } from "./slot-editor";
import { SourcePanel, type UploadedDoc, type UploadingDoc } from "./source-panel";
import { Spinner } from "@/components/ui/spinner";

export interface BlueprintSubmission {
  templateId: string;
  templateName: string;
  blueprint: Blueprint;
  settings: {
    subject: string;
    academicClass: string;
    board: string;
    difficulty: string;
    numberOfSets: string;
    /** Mathematics only: Standard (041) vs Basic (241). Ignored elsewhere. */
    mathLevel: string;
  };
  instructions: string;
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onGenerate: (submission: BlueprintSubmission) => void;
  generating?: boolean;

  // Sources are owned by the page, not the modal: the same uploads feed a
  // regeneration after the modal closes, and an in-flight ingest must survive
  // the teacher dismissing this dialog.
  uploadedDocs: UploadedDoc[];
  uploadingDocs: UploadingDoc[];
  hsatSources: AppliedHsatSource[];
  onFiles: (files: File[]) => void;
  onRemoveDoc: (id: string) => void;
  onDismissUpload: (tempId: string) => void;
  onRemoveHsat: (id: string) => void;
  onOpenHsatPicker: () => void;
  /** "Use anyway" on a subject-mismatch warning — owned by the page, because
   *  the override lives on the source and outlives this dialog. */
  onAcceptSubjectMismatch?: (id: string) => void;

  detectedSubject?: string;

  /**
   * A plain-English brief typed in the editor's Studio dock. When present the
   * Builder opens on "Describe It Yourself", already resolved from it.
   */
  initialInstructions?: string;

  /**
   * A template chosen elsewhere — "Use" on the Templates page. The Builder
   * opens on it already resolved, skipping the picker the teacher just used a
   * richer version of. Built-in ids and saved-template ids both work; the
   * catalog decides which is which.
   */
  initialTemplateId?: string;
}

/** The catalog's prose template — `services/template_catalog.py`. */
const DESCRIBE_TEMPLATE_ID = "describe-it-yourself";

type Step = "template" | "sources" | "questions";

const STEPS: { id: Step; label: string }[] = [
  { id: "template", label: "Template" },
  { id: "sources", label: "Sources" },
  { id: "questions", label: "Questions" },
];

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


export function BlueprintModal({
  open,
  onOpenChange,
  onGenerate,
  generating = false,
  uploadedDocs,
  uploadingDocs,
  hsatSources,
  onFiles,
  onRemoveDoc,
  onDismissUpload,
  onRemoveHsat,
  onOpenHsatPicker,
  onAcceptSubjectMismatch,
  detectedSubject,
  initialInstructions,
  initialTemplateId,
}: Props) {
  const [step, setStep] = React.useState<Step>("template");
  const [builtin, setBuiltin] = React.useState<BuiltinTemplate[]>([]);
  const [saved, setSaved] = React.useState<PaperTemplate[]>([]);
  const [catalogLoading, setCatalogLoading] = React.useState(false);
  const [questionTypes, setQuestionTypes] = React.useState<QuestionTypeOption[]>([]);

  const [templateId, setTemplateId] = React.useState<string | null>(null);
  const [templateName, setTemplateName] = React.useState("");
  const [templateKind, setTemplateKind] = React.useState<string>("");
  const [blueprint, setBlueprint] = React.useState<Blueprint>(EMPTY_BLUEPRINT);
  const [resolving, setResolving] = React.useState(false);

  const [subject, setSubject] = React.useState(detectedSubject || "Science");
  const [academicClass, setAcademicClass] = React.useState("10");
  const [difficulty, setDifficulty] = React.useState("medium");
  const [numberOfSets, setNumberOfSets] = React.useState("1");
  const [mathLevel, setMathLevel] = React.useState("standard");
  const [instructions, setInstructions] = React.useState("");

  const [saveName, setSaveName] = React.useState("");
  const [savingTemplate, setSavingTemplate] = React.useState(false);

  // A detected subject should fill the field, never fight the teacher who has
  // already corrected it — so this only applies while nothing is chosen.
  React.useEffect(() => {
    if (detectedSubject && !templateId) setSubject(detectedSubject);
  }, [detectedSubject, templateId]);

  React.useEffect(() => {
    if (!open) return;
    let active = true;
    setCatalogLoading(true);
    fetchTemplateCatalog()
      .then((data) => {
        if (!active) return;
        setBuiltin(data.builtin);
        setSaved(data.templates);
      })
      .catch((error) => {
        console.error("Template catalog failed to load:", error);
        toast.error("Could not load templates. Check your connection.");
      })
      .finally(() => {
        if (active) setCatalogLoading(false);
      });
    return () => {
      active = false;
    };
  }, [open]);

  React.useEffect(() => {
    if (!open) return;
    let active = true;
    fetchQuestionTypeMenu(subject)
      .then((types) => active && setQuestionTypes(types))
      .catch((error) => console.error("Question type menu failed:", error));
    return () => {
      active = false;
    };
  }, [open, subject]);

  const applyTemplate = React.useCallback(
    // `briefOverride` exists because the Studio dock seeds the brief and
    // resolves in the same tick. Reading `instructions` from the closure there
    // would send the PREVIOUS value (state has not committed yet), so the
    // blueprint would come back planned from the wrong text — or from nothing
    // at all on the first use.
    async (id: string, kind: string, briefOverride?: string) => {
      const brief = briefOverride ?? instructions;
      setTemplateId(id);
      setTemplateKind(kind);
      const match =
        builtin.find((t) => t.id === id) ?? saved.find((t) => t.id === id);
      setTemplateName(match?.name ?? "");

      // A board template carries its own subject and class; adopting them
      // saves the teacher re-picking what the card already said.
      const builtinMatch = builtin.find((t) => t.id === id);
      if (builtinMatch?.subject) setSubject(builtinMatch.subject);
      if (builtinMatch?.academicClass) setAcademicClass(builtinMatch.academicClass);

      setResolving(true);
      try {
        const result = await resolveTemplate({
          templateId: id,
          subject: builtinMatch?.subject || subject,
          academicClass: builtinMatch?.academicClass || academicClass,
          difficulty,
          instructions: brief,
        });
        setBlueprint(recomputeTotals(result.blueprint.slots));
        if (result.template?.instructions) {
          setInstructions(result.template.instructions);
        }
        // Always hand over to Sources. Skipping ahead to Questions when the
        // template happened to resolve slots was a shortcut that skipped the
        // one step the paper cannot be generated without — a teacher who
        // never sees step 2 has no chapter attached, and finds out only when
        // generation produces nothing.
        setStep("sources");
      } catch (error: any) {
        console.error("Template resolve failed:", error);
        toast.error(
          error?.message || "That template could not be opened. Try another.",
        );
        setBlueprint(EMPTY_BLUEPRINT);
      } finally {
        setResolving(false);
      }
    },
    [builtin, saved, subject, academicClass, difficulty, instructions],
  );

  // ── Opened from the Studio dock with a brief ────────────────────────────
  // "Class 10 Science mid-term, 80 marks" typed on the right of the editor is
  // exactly the input "Describe It Yourself" takes, so the Builder opens
  // already resolved on it rather than on a template grid the teacher has to
  // read past to get back to what they just said.
  //
  // The ref is what stops this re-firing: `applyTemplate` sets state this
  // effect depends on, so without a record of what has already been applied it
  // would resolve the same brief on every render pass.
  const appliedBriefRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!open) {
      appliedBriefRef.current = null;
      return;
    }
    const brief = (initialInstructions || "").trim();
    if (!brief || appliedBriefRef.current === brief) return;
    // Wait for the catalog so the template's name and kind are known.
    if (builtin.length === 0) return;

    appliedBriefRef.current = brief;
    setInstructions(brief);
    void applyTemplate(DESCRIBE_TEMPLATE_ID, "instructions", brief);
  }, [open, initialInstructions, builtin.length, applyTemplate]);

  // ── Opened from the Templates page with a chosen template ───────────────
  // Same shape as the brief handoff above, and guarded the same way: the
  // effect's own action changes state it depends on, so without a record of
  // what was already applied it would re-resolve on every render.
  //
  // A brief wins if both arrive. "Describe It Yourself" resolved from what the
  // teacher just typed is a more specific instruction than a template id that
  // has been sitting in the store since the last navigation.
  const appliedTemplateRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!open) {
      appliedTemplateRef.current = null;
      return;
    }
    const wanted = (initialTemplateId || "").trim();
    if (!wanted || appliedTemplateRef.current === wanted) return;
    if ((initialInstructions || "").trim()) return;
    // Wait for the catalog: `applyTemplate` reads the entry for its name, kind
    // and — for a board template — the subject and class it should adopt.
    if (builtin.length === 0 && saved.length === 0) return;

    const match =
      saved.find((t) => t.id === wanted) ?? builtin.find((t) => t.id === wanted);
    if (!match) {
      // Deleted between navigating and arriving. Leaving the picker open is
      // the right outcome; a toast about an id the teacher never saw is not.
      appliedTemplateRef.current = wanted;
      return;
    }

    appliedTemplateRef.current = wanted;
    void applyTemplate(
      wanted,
      "builtin" in match && match.builtin ? match.kind : "saved",
    );
  }, [
    open,
    initialTemplateId,
    initialInstructions,
    builtin,
    saved,
    applyTemplate,
  ]);

  const handleSlotsChange = (slots: BlueprintSlot[]) => {
    setBlueprint(recomputeTotals(slots));
  };

  const handleDeleteTemplate = async (template: PaperTemplate) => {
    try {
      await deletePaperTemplate(template.id);
      setSaved((prev) => prev.filter((t) => t.id !== template.id));
      if (templateId === template.id) {
        setTemplateId(null);
        setBlueprint(EMPTY_BLUEPRINT);
      }
      toast.success(`Deleted "${template.name}"`);
    } catch (error: any) {
      toast.error(error?.message || "Could not delete that template.");
    }
  };

  const handleSaveTemplate = async () => {
    const name = saveName.trim();
    if (!name) {
      toast.error("Give your template a name first.");
      return;
    }
    setSavingTemplate(true);
    try {
      const template = await savePaperTemplate({
        name,
        instructions,
        settings: { subject, academicClass, difficulty, numberOfSets, mathLevel },
        blueprint: { slots: blueprint.slots },
        baseTemplateId: templateId ?? "",
        sourceConfig: {
          pdfSourceIds: uploadedDocs.map((d) => d.id),
          hsatSourceIds: hsatSources.map((s) => s.id),
        },
      });
      setSaved((prev) => [
        template,
        ...prev.filter((t) => t.id !== template.id),
      ]);
      setSaveName("");
      toast.success(`Saved "${name}" — it will be waiting next time.`);
    } catch (error: any) {
      toast.error(error?.message || "Could not save that template.");
    } finally {
      setSavingTemplate(false);
    }
  };

  const canGenerate =
    blueprint.totalQuestions > 0 && !generating && !resolving;

  const handleGenerate = () => {
    if (!canGenerate) return;
    onGenerate({
      templateId: templateId ?? "",
      templateName,
      blueprint,
      settings: {
        subject,
        academicClass,
        board: "CBSE",
        difficulty,
        numberOfSets,
        mathLevel,
      },
      instructions,
    });
  };

  const stepIndex = STEPS.findIndex((s) => s.id === step);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        showCloseButton={false}
        className="flex h-[min(88vh,900px)] w-[min(96vw,1100px)] max-w-none flex-col gap-0 overflow-hidden p-0 sm:max-w-none"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-5 py-3.5">
          <div>
            <DialogTitle className="text-base font-semibold">
              Create a paper
            </DialogTitle>
            <DialogDescription className="text-xs">
              Pick a starting point, then change anything you like.
            </DialogDescription>
          </div>
          <button
            type="button"
            aria-label="Close"
            onClick={() => onOpenChange(false)}
            className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <X className="size-4" />
          </button>
        </div>

        <div className="flex min-h-0 flex-1">
          {/* Step rail */}
          <nav className="hidden w-48 shrink-0 border-r border-border bg-muted/20 p-3 sm:block">
            <ol className="space-y-1">
              {STEPS.map((entry, i) => {
                const active = entry.id === step;
                const reachable = i === 0 || templateId !== null;
                const done = i < stepIndex && templateId !== null;
                return (
                  <li key={entry.id}>
                    <button
                      type="button"
                      disabled={!reachable}
                      onClick={() => setStep(entry.id)}
                      className={cn(
                        "flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm transition-colors",
                        active
                          ? "bg-primary text-primary-foreground"
                          : reachable
                            ? "text-foreground hover:bg-muted"
                            : "cursor-not-allowed text-muted-foreground/50",
                      )}
                    >
                      <span
                        className={cn(
                          "flex size-5 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold",
                          active
                            ? "bg-primary-foreground/20"
                            : done
                              ? "bg-primary/15 text-primary"
                              : "bg-muted-foreground/15",
                        )}
                      >
                        {done ? <Check className="size-3" /> : i + 1}
                      </span>
                      {entry.label}
                    </button>
                  </li>
                );
              })}
            </ol>

            {/* Paper settings live in the rail: they apply to every step, and
                putting them in one step would make the other two lie about
                what they were configuring. */}
            {templateId ? (
              <div className="mt-5 space-y-3 border-t border-border pt-4">
                <div className="space-y-1">
                  <Label className="text-[10px] uppercase tracking-wide text-muted-foreground">
                    Class
                  </Label>
                  <select
                    value={academicClass}
                    onChange={(e) => setAcademicClass(e.target.value)}
                    className="h-8 w-full rounded-lg border border-input bg-transparent px-2 text-xs"
                  >
                    {CLASSES.map((c) => (
                      <option key={c} value={c}>
                        Class {c}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1">
                  <Label className="text-[10px] uppercase tracking-wide text-muted-foreground">
                    Subject
                  </Label>
                  <select
                    value={subject}
                    onChange={(e) => setSubject(e.target.value)}
                    className="h-8 w-full rounded-lg border border-input bg-transparent px-2 text-xs"
                  >
                    {SUBJECTS.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1">
                  <Label className="text-[10px] uppercase tracking-wide text-muted-foreground">
                    Difficulty
                  </Label>
                  <select
                    value={difficulty}
                    onChange={(e) => setDifficulty(e.target.value)}
                    className="h-8 w-full rounded-lg border border-input bg-transparent px-2 text-xs capitalize"
                  >
                    {DIFFICULTIES.map((d) => (
                      <option key={d} value={d}>
                        {d}
                      </option>
                    ))}
                  </select>
                </div>
                {/* Standard (041) and Basic (241) share the identical A–E
                    skeleton and differ only in cognitive-band target, so this
                    is a selection-time flag rather than a structural choice.
                    Shown only where it means anything. */}
                {subject === "Mathematics" ? (
                  <div className="space-y-1">
                    <Label className="text-[10px] uppercase tracking-wide text-muted-foreground">
                      Maths level
                    </Label>
                    <select
                      value={mathLevel}
                      onChange={(e) => setMathLevel(e.target.value)}
                      className="h-8 w-full rounded-lg border border-input bg-transparent px-2 text-xs"
                    >
                      <option value="standard">Standard (041)</option>
                      <option value="basic">Basic (241)</option>
                    </select>
                  </div>
                ) : null}
                <div className="space-y-1">
                  <Label className="text-[10px] uppercase tracking-wide text-muted-foreground">
                    Sets
                  </Label>
                  <select
                    value={numberOfSets}
                    onChange={(e) => setNumberOfSets(e.target.value)}
                    className="h-8 w-full rounded-lg border border-input bg-transparent px-2 text-xs"
                  >
                    <option value="1">1 set (A)</option>
                    <option value="2">2 sets (A, B)</option>
                    <option value="3">3 sets (A, B, C)</option>
                  </select>
                </div>
              </div>
            ) : null}
          </nav>

          {/* Step content */}
          <div className="min-w-0 flex-1 overflow-y-auto p-6">
            {resolving ? (
              <Spinner size="page" label="Preparing the blueprint…" />
            ) : step === "template" ? (
              <TemplatePickerGrid
                builtin={builtin}
                saved={saved}
                selectedId={templateId}
                onSelect={applyTemplate}
                onDelete={handleDeleteTemplate}
                loading={catalogLoading}
              />
            ) : step === "sources" ? (
              <div className="space-y-5">
                <SourcePanel
                  uploadedDocs={uploadedDocs}
                  uploadingDocs={uploadingDocs}
                  hsatSources={hsatSources}
                  savedCount={blueprint.savedCount}
                  onFiles={onFiles}
                  onRemoveDoc={onRemoveDoc}
                  onDismissUpload={onDismissUpload}
                  onRemoveHsat={onRemoveHsat}
                  onOpenHsatPicker={onOpenHsatPicker}
                  // The paper's own subject is the thing an uploaded chapter
                  // has to agree with — cross-checking the uploads only
                  // against each other lets a single wrong-subject PDF pass.
                  expectedSubject={subject}
                  onAcceptSubjectMismatch={onAcceptSubjectMismatch}
                />

                {templateKind === "instructions" || instructions ? (
                  <div className="space-y-1.5">
                    <Label className="text-xs font-semibold">
                      Describe the paper
                    </Label>
                    <textarea
                      value={instructions}
                      onChange={(e) => setInstructions(e.target.value)}
                      rows={4}
                      placeholder="e.g. Weekly test on photosynthesis, mostly recall, 20 marks, half an hour"
                      className="w-full resize-y rounded-lg border border-input bg-transparent px-3 py-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
                    />
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={!instructions.trim() || resolving}
                      onClick={() =>
                        templateId && applyTemplate(templateId, templateKind)
                      }
                    >
                      Plan the paper from this
                    </Button>
                  </div>
                ) : null}
              </div>
            ) : (
              <SlotEditor
                slots={blueprint.slots}
                questionTypes={questionTypes}
                totals={blueprint}
                onChange={handleSlotsChange}
              />
            )}
          </div>
        </div>

        {/* Footer: live totals + actions */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border bg-muted/20 px-5 py-3">
          <div className="flex items-center gap-4 text-xs">
            <span className="font-semibold tabular-nums">
              {blueprint.totalQuestions} question
              {blueprint.totalQuestions === 1 ? "" : "s"}
            </span>
            <span className="font-semibold tabular-nums">
              {blueprint.totalMarks} marks
            </span>
            {blueprint.savedCount > 0 ? (
              <span className="text-muted-foreground tabular-nums">
                {blueprint.savedCount} from bank · {blueprint.generatedCount} new
              </span>
            ) : null}
          </div>

          <div className="flex items-center gap-2">
            {blueprint.totalQuestions > 0 ? (
              <div className="flex items-center gap-1.5">
                <Input
                  value={saveName}
                  onChange={(e) => setSaveName(e.target.value)}
                  placeholder="Save as template…"
                  className="h-8 w-40 text-xs"
                />
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-8"
                  disabled={!saveName.trim() || savingTemplate}
                  onClick={handleSaveTemplate}
                >
                  {savingTemplate ? (
                    <Spinner className="size-3.5" />
                  ) : (
                    <Save className="size-3.5" />
                  )}
                </Button>
              </div>
            ) : null}

            {stepIndex > 0 ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-8"
                onClick={() => setStep(STEPS[stepIndex - 1].id)}
              >
                <ArrowLeft className="size-3.5" />
                Back
              </Button>
            ) : null}

            {stepIndex < STEPS.length - 1 ? (
              <Button
                type="button"
                size="sm"
                className="h-8"
                disabled={!templateId}
                onClick={() => setStep(STEPS[stepIndex + 1].id)}
              >
                Next
                <ArrowRight className="size-3.5" />
              </Button>
            ) : (
              <Button
                type="button"
                size="sm"
                className="h-8"
                disabled={!canGenerate}
                onClick={handleGenerate}
              >
                {generating ? (
                  <>
                    <Spinner className="size-3.5" />
                    Generating…
                  </>
                ) : (
                  <>
                    Generate {blueprint.totalQuestions} Questions
                  </>
                )}
              </Button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
