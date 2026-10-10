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
  Cpu,
  FlaskConical,
  Globe,
  Languages,
  Monitor,
  Save,
  Sigma,
  Sparkles,
  X,
  type LucideIcon,
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
  type DetectedSettings,
  type QuestionTypeOption,
} from "@/lib/api-client";
import { recomputeTotals } from "@/lib/blueprint-totals";
import type { AppliedHsatSource } from "@/lib/hsat-source";
import { PAPER_CLASSES, PAPER_SUBJECTS, paperSubjectEntry } from "@/lib/subject";

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

/**
 * Paper first, template second. The template picker browses by class and
 * subject, so it opens on the ones the teacher has just set — and the chapters
 * attached there are what every template is generated from anyway.
 */
const STEPS: { id: Step; label: string }[] = [
  // Class, subject, difficulty and sets are set on this step, beside the
  // chapters they must agree with — hence the label.
  { id: "sources", label: "Paper & sources" },
  { id: "template", label: "Template" },
  { id: "questions", label: "Questions" },
];

const CLASSES = PAPER_CLASSES;
const SUBJECTS = PAPER_SUBJECTS;
const subjectEntry = paperSubjectEntry;
const DIFFICULTIES = ["easy", "medium", "hard"];

/** Questions is the one step that needs a template; the rest are always open. */
function stepReachable(step: Step, templateId: string | null) {
  return step !== "questions" || templateId !== null;
}

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
  const [step, setStep] = React.useState<Step>("sources");
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

  //: What the last resolve read off the brief or the card, kept so the rail can
  //: say which of its values came from the teacher's own words rather than
  //: from a default they never chose.
  const [readFromBrief, setReadFromBrief] = React.useState<DetectedSettings>({});
  //: What the designer had to correct — a stated 80-mark total that the
  //: structure misses, and the like.
  const [designNotes, setDesignNotes] = React.useState<string[]>([]);

  /**
   * Write what the resolve settled into the rail.
   *
   * This is the whole fix for a brief being read and then ignored. "Class 9
   * Maths, 80 marks, one set" resolved a blueprint out of the prose and then
   * generated with the rail's untouched defaults — Science, Class 10, 1 set —
   * because nothing ever carried the teacher's own words back into the form
   * that generation actually reads.
   *
   * Two rules, both deliberate. Only keys the resolve genuinely settled are
   * present, so an unstated subject leaves the teacher's choice alone instead
   * of blanking it. And it lands in the visible controls rather than in a
   * hidden override: a paper that silently generates as Class 9 is the same
   * bug as one that silently generates as Class 10, just pointing the other
   * way. The teacher has to be able to see it and disagree.
   */
  const applyDetected = React.useCallback((detected?: DetectedSettings) => {
    setReadFromBrief(detected ?? {});
    if (!detected) return;
    if (detected.subject) setSubject(detected.subject);
    if (detected.academicClass) setAcademicClass(detected.academicClass);
    if (detected.numberOfSets) setNumberOfSets(detected.numberOfSets);
    if (detected.difficulty) setDifficulty(detected.difficulty);
  }, []);

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
    // The class ranks the menu — its usual types are suggested first — so the
    // menu is refetched when the class changes, as it is for the subject.
    fetchQuestionTypeMenu(subject, undefined, academicClass)
      .then((types) => active && setQuestionTypes(types))
      .catch((error) => console.error("Question type menu failed:", error));
    return () => {
      active = false;
    };
  }, [open, subject, academicClass]);

  const applyTemplate = React.useCallback(
    // `options.brief` exists because the Studio dock seeds the brief and
    // resolves in the same tick. Reading `instructions` from the closure there
    // would send the PREVIOUS value (state has not committed yet), so the
    // blueprint would come back planned from the wrong text — or from nothing
    // at all on the first use.
    //
    // `options.academicClass` is the class tab a ready-made paper was picked
    // under: a Class 3–5 test chosen on the Class 3 tab is a Class 3 paper,
    // whatever the rail said before.
    async (
      id: string,
      kind: string,
      options: { brief?: string; academicClass?: string; nextStep?: Step } = {},
    ) => {
      const brief = options.brief ?? instructions;
      const requestedClass = options.academicClass || academicClass;
      if (options.academicClass) setAcademicClass(options.academicClass);
      setTemplateId(id);
      setTemplateKind(kind);
      const match =
        builtin.find((t) => t.id === id) ?? saved.find((t) => t.id === id);
      setTemplateName(match?.name ?? "");

      // A board template carries its own subject and class, so they seed the
      // REQUEST — but what gets adopted into the rail is what comes back, via
      // `detected`. The resolve is the only place that can weigh a card's
      // stated class against a brief that names a different one, so it is the
      // one that decides; the client just applies the answer.
      const builtinMatch = builtin.find((t) => t.id === id);

      setResolving(true);
      try {
        const result = await resolveTemplate({
          templateId: id,
          subject: builtinMatch?.subject || subject,
          academicClass: builtinMatch?.academicClass || requestedClass,
          difficulty,
          instructions: brief,
        });
        setBlueprint(recomputeTotals(result.blueprint.slots));
        if (result.template?.instructions) {
          setInstructions(result.template.instructions);
        }
        applyDetected(result.detected);
        setDesignNotes(result.corrections ?? []);
        // Picked here, the template hands over to its questions — the paper
        // and its chapters were set on the step before. "Describe It
        // Yourself" with nothing written yet stays put: its box is on this
        // step. A template applied on arrival (a Studio brief, "Use" on the
        // Templates page) says where to land instead, because that teacher
        // has not seen the chapters step yet.
        const emptyBrief =
          kind === "instructions" && result.blueprint.slots.length === 0;
        setStep(options.nextStep ?? (emptyBrief ? "template" : "questions"));
      } catch (error: any) {
        console.error("Template resolve failed:", error);
        toast.error(
          error?.message || "That template could not be opened. Try another.",
        );
        setBlueprint(EMPTY_BLUEPRINT);
        setReadFromBrief({});
        setDesignNotes([]);
      } finally {
        setResolving(false);
      }
    },
    [builtin, saved, subject, academicClass, difficulty, instructions, applyDetected],
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
      setReadFromBrief({});
      setDesignNotes([]);
      return;
    }
    const brief = (initialInstructions || "").trim();
    if (!brief || appliedBriefRef.current === brief) return;
    // Wait for the catalog so the template's name and kind are known.
    if (builtin.length === 0) return;

    appliedBriefRef.current = brief;
    setInstructions(brief);
    void applyTemplate(DESCRIBE_TEMPLATE_ID, "instructions", {
      brief,
      nextStep: "sources",
    });
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
      { nextStep: "sources" },
    );
  }, [
    open,
    initialTemplateId,
    initialInstructions,
    builtin,
    saved,
    applyTemplate,
  ]);

  // ── Class and subject, read off the attached chapters ───────────────────
  // The first source that knows what it is wins: a library book carries its
  // grade and subject, an upload carries the subject the backend detected.
  // First, not latest, so a second off-subject chapter is flagged by the
  // mismatch warning instead of quietly flipping the whole paper.
  const sourceHint = React.useMemo(() => {
    const book = hsatSources.find((s) => s.subject);
    if (book) {
      return { subject: book.subject, academicClass: book.grade, from: book.book };
    }
    const doc = uploadedDocs.find((d) => d.subject);
    return doc ? { subject: doc.subject!, academicClass: "", from: doc.name } : null;
  }, [hsatSources, uploadedDocs]);

  // A board paper or class starter fixes its subject — a Maths blueprint must
  // not silently become a Science paper because a Science book was attached.
  // There the hint is offered as a one-click switch rather than applied.
  const templateSubject = builtin.find((t) => t.id === templateId)?.subject;
  const hintKey = sourceHint
    ? `${sourceHint.subject}|${sourceHint.academicClass}|${sourceHint.from}`
    : "";
  const [flashKey, setFlashKey] = React.useState(0);
  const appliedHintRef = React.useRef("");
  React.useEffect(() => {
    if (!sourceHint || appliedHintRef.current === hintKey) return;
    appliedHintRef.current = hintKey;
    if (templateSubject) return;
    if (subjectEntry(sourceHint.subject)) setSubject(sourceHint.subject);
    if (CLASSES.includes(sourceHint.academicClass)) {
      setAcademicClass(sourceHint.academicClass);
    }
    setFlashKey((k) => k + 1);
  }, [sourceHint, hintKey, templateSubject]);

  const hintMatches =
    !!sourceHint &&
    subjectEntry(sourceHint.subject) === subjectEntry(subject) &&
    (!sourceHint.academicClass || sourceHint.academicClass === academicClass);

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

  // The rail's own labels, so the receipt below reads like the controls it is
  // reporting on rather than like a dump of an API response.
  const briefChips: string[] = [];
  if (readFromBrief.academicClass) briefChips.push(`Class ${readFromBrief.academicClass}`);
  if (readFromBrief.subject) briefChips.push(readFromBrief.subject);
  if (readFromBrief.totalMarks) briefChips.push(`${readFromBrief.totalMarks} marks`);
  if (readFromBrief.numberOfSets) {
    briefChips.push(
      `${readFromBrief.numberOfSets} set${readFromBrief.numberOfSets === "1" ? "" : "s"}`,
    );
  }
  if (readFromBrief.difficulty) {
    briefChips.push(
      readFromBrief.difficulty[0].toUpperCase() + readFromBrief.difficulty.slice(1),
    );
  }

  const stepIndex = STEPS.findIndex((s) => s.id === step);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        showCloseButton={false}
        className="builder-dialog flex h-[min(92vh,980px)] w-[min(96vw,1280px)] max-w-none flex-col gap-0 overflow-hidden p-0 sm:max-w-none"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-5 py-3.5">
          <div>
            <DialogTitle className="text-base font-semibold">
              Create a paper
            </DialogTitle>
            <DialogDescription className="text-xs">
              Set up the paper, pick a template, then change anything you like.
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

        {/* Step dots, below `sm` only. The rail hides at that width, and with
            only Back and Next left this becomes the sequential wizard the
            header comment argues against. Same reachability rules as the
            rail, so it cannot offer a step the rail would refuse. */}
        <nav
          aria-label="Steps"
          className="flex shrink-0 items-center gap-1 border-b border-border bg-muted/20 px-3 py-2 sm:hidden"
        >
          {STEPS.map((entry, i) => {
            const active = entry.id === step;
            const reachable = stepReachable(entry.id, templateId);
            const done =
              i < stepIndex && (entry.id !== "template" || templateId !== null);
            return (
              <button
                key={entry.id}
                type="button"
                disabled={!reachable}
                onClick={() => setStep(entry.id)}
                aria-current={active ? "step" : undefined}
                className={cn(
                  "flex flex-1 items-center justify-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors",
                  active
                    ? "bg-primary text-primary-foreground"
                    : reachable
                      ? "text-foreground hover:bg-muted"
                      : "cursor-not-allowed text-muted-foreground/50",
                )}
              >
                <span
                  className={cn(
                    "flex size-4 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold",
                    active
                      ? "bg-primary-foreground/20"
                      : done
                        ? "bg-primary/15 text-primary"
                        : "bg-muted-foreground/15",
                  )}
                >
                  {done ? <Check className="size-2.5" /> : i + 1}
                </span>
                <span className="truncate">{entry.label}</span>
              </button>
            );
          })}
        </nav>

        <div className="flex min-h-0 flex-1">
          {/* Step rail */}
          <nav className="hidden w-48 shrink-0 border-r border-border bg-muted/20 p-3 sm:block">
            <ol className="space-y-1">
              {STEPS.map((entry, i) => {
                const active = entry.id === step;
                const reachable = stepReachable(entry.id, templateId);
                const done =
                  i < stepIndex && (entry.id !== "template" || templateId !== null);
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
          </nav>

          {/* Step content */}
          <div className="min-w-0 flex-1 overflow-y-auto p-6">
            {/* A receipt for what the brief was taken to mean.
                Applying the teacher's words to the rail silently would trade
                one invisible decision for another, so what was read is stated
                where they are about to press Generate — and every chip
                corresponds to a control they can still change. */}
            {!resolving && (briefChips.length > 0 || designNotes.length > 0) ? (
              <div className="mb-5 rounded-lg border border-border bg-muted/30 px-3.5 py-3">
                {briefChips.length > 0 ? (
                  <>
                    <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                      Read from what you wrote
                    </p>
                    <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                      {briefChips.map((chip) => (
                        <span
                          key={chip}
                          className="rounded-full border border-border bg-background px-2 py-0.5 text-[11px] text-foreground"
                        >
                          {chip}
                        </span>
                      ))}
                      <span className="text-[11px] text-muted-foreground">
                        — you can change any of it.
                      </span>
                    </div>
                  </>
                ) : null}
                {designNotes.length > 0 ? (
                  <ul
                    className={cn(
                      "space-y-1 text-[11px] leading-relaxed text-muted-foreground",
                      briefChips.length > 0 && "mt-2.5 border-t border-border pt-2.5",
                    )}
                  >
                    {designNotes.map((note) => (
                      <li key={note}>{note}</li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}

            <div key={resolving ? "resolving" : step} className="builder-step">
            {resolving ? (
              <Spinner size="page" label="Preparing the blueprint…" />
            ) : step === "template" ? (
              <div className="space-y-6">
                {/* The brief for "Describe It Yourself" (or an adaptive saved
                    template) lives with the template it drives. */}
                {templateKind === "instructions" || instructions ? (
                  <div className="space-y-1.5 border border-border bg-card p-4">
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
                <TemplatePickerGrid
                  builtin={builtin}
                  saved={saved}
                  selectedId={templateId}
                  onSelect={(id, kind, options) => void applyTemplate(id, kind, options)}
                  onDelete={handleDeleteTemplate}
                  loading={catalogLoading}
                  academicClass={academicClass}
                  subject={subject}
                />
              </div>
            ) : step === "sources" ? (
              <div className="space-y-5">
                <PaperForPanel
                  academicClass={academicClass}
                  subject={subject}
                  difficulty={difficulty}
                  numberOfSets={numberOfSets}
                  mathLevel={mathLevel}
                  onClassChange={setAcademicClass}
                  onSubjectChange={setSubject}
                  onDifficultyChange={setDifficulty}
                  onSetsChange={setNumberOfSets}
                  onMathLevelChange={setMathLevel}
                  hint={sourceHint}
                  hintMatches={hintMatches}
                  flashKey={flashKey}
                  onApplyHint={() => {
                    if (!sourceHint) return;
                    setSubject(sourceHint.subject);
                    if (CLASSES.includes(sourceHint.academicClass)) {
                      setAcademicClass(sourceHint.academicClass);
                    }
                    setFlashKey((k) => k + 1);
                  }}
                />
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

              </div>
            ) : (
              <SlotEditor
                slots={blueprint.slots}
                questionTypes={questionTypes}
                totals={blueprint}
                academicClass={academicClass}
                onChange={handleSlotsChange}
              />
            )}
            </div>
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
                disabled={!stepReachable(STEPS[stepIndex + 1].id, templateId)}
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


const SUBJECT_ICONS: Record<string, LucideIcon> = {
  Science: FlaskConical,
  "Social Science": Globe,
  Mathematics: Sigma,
  English: Languages,
  Hindi: Languages,
  Telugu: Languages,
  Sanskrit: Languages,
  "Computer Science": Cpu,
  ICT: Monitor,
};

const DIFFICULTY_DOTS: Record<string, string> = {
  easy: "bg-success",
  medium: "bg-warning",
  hard: "bg-destructive",
};

const SET_OPTIONS = [
  { value: "1", label: "A" },
  { value: "2", label: "A · B" },
  { value: "3", label: "A · B · C" },
];

/**
 * The square chip the builder uses for every small choice — the same border,
 * weight and filled-primary selected state as the template cards above it.
 */
const choiceChip = (active: boolean) =>
  cn(
    "flex items-center justify-center gap-1.5 border px-3.5 py-2 text-sm font-medium tabular-nums transition-all duration-200 ease-[var(--ease)]",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
    active
      ? "border-primary bg-primary text-primary-foreground shadow-sm shadow-primary/25"
      : "border-border bg-background hover:-translate-y-0.5 hover:border-primary/50 hover:text-primary",
  );

function ChoiceGroup({
  label,
  options,
  value,
  onChange,
  chipClassName,
}: {
  label: string;
  options: { value: string; label: React.ReactNode }[];
  value: string;
  onChange: (value: string) => void;
  chipClassName?: string;
}) {
  return (
    <div>
      <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <div role="radiogroup" aria-label={label} className="flex flex-wrap gap-2">
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={option.value === value}
            onClick={() => onChange(option.value)}
            className={cn(choiceChip(option.value === value), chipClassName)}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}

/**
 * The paper's identity — class, subject, difficulty, sets — at the top of the
 * Sources step. These used to be selects in the step rail as well, which left
 * two controls for the same value a few hundred pixels apart; now this is the
 * only place they are set, right beside the chapters they must agree with,
 * and it fills itself in from those chapters when it can.
 *
 * The header reads back the whole choice as one line ("Class 10 · Science"),
 * so a wrong default is impossible to miss before anything is generated. It
 * borrows the template card's vocabulary — accent bar, filled icon tile — so
 * the paper chosen on step 1 visibly carries on into step 2.
 */
function PaperForPanel({
  academicClass,
  subject,
  difficulty,
  numberOfSets,
  mathLevel,
  onClassChange,
  onSubjectChange,
  onDifficultyChange,
  onSetsChange,
  onMathLevelChange,
  hint,
  hintMatches,
  flashKey,
  onApplyHint,
}: {
  academicClass: string;
  subject: string;
  difficulty: string;
  numberOfSets: string;
  mathLevel: string;
  onClassChange: (value: string) => void;
  onSubjectChange: (value: string) => void;
  onDifficultyChange: (value: string) => void;
  onSetsChange: (value: string) => void;
  onMathLevelChange: (value: string) => void;
  hint: { subject: string; academicClass: string; from: string } | null;
  hintMatches: boolean;
  flashKey: number;
  onApplyHint: () => void;
}) {
  const activeSubject = subjectEntry(subject);
  const isMaths = activeSubject === "Mathematics";
  const setsLabel =
    SET_OPTIONS.find((o) => o.value === numberOfSets)?.label ?? numberOfSets;

  return (
    <section
      key={flashKey}
      className={cn(
        "relative overflow-hidden border border-border bg-card",
        flashKey > 0 && "builder-flash",
      )}
    >
      <span aria-hidden className="absolute inset-y-0 left-0 w-1 bg-primary" />

      {/* Header: the choice read back as one line */}
      <div className="relative flex flex-wrap items-center gap-4 border-b border-border px-5 py-4">
        <span
          key={activeSubject ?? subject}
          className="builder-step flex size-11 shrink-0 items-center justify-center bg-primary text-primary-foreground"
        >
          {React.createElement(
            (activeSubject && SUBJECT_ICONS[activeSubject]) || BookOpen,
            { className: "size-5" },
          )}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            This paper is for
          </p>
          <h3 className="truncate text-base font-semibold leading-snug">
            Class {academicClass} · {subject}
          </h3>
          <p className="text-xs text-muted-foreground">
            <span className="capitalize">{difficulty}</span> ·{" "}
            {numberOfSets === "1" ? "1 set" : `${numberOfSets} sets`} ({setsLabel})
            {isMaths ? ` · ${mathLevel === "basic" ? "Basic (241)" : "Standard (041)"}` : ""}
          </p>
        </div>
        {hint && hintMatches ? (
          <span className="flex max-w-full items-center gap-1.5 bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary">
            <Sparkles className="size-3.5 shrink-0" />
            <span className="truncate">Picked up from {hint.from}</span>
          </span>
        ) : null}
      </div>

      <div className="relative space-y-5 p-5">
        {hint && !hintMatches ? (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border border-warning/40 bg-warning/5 px-3 py-2">
            <p className="min-w-0 flex-1 text-xs leading-relaxed text-warning">
              <strong>{hint.from}</strong> looks like{" "}
              <strong>
                {hint.academicClass ? `Class ${hint.academicClass} ` : ""}
                {hint.subject}
              </strong>
              , but this paper is set to Class {academicClass} {subject}.
            </p>
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-7 px-2 text-xs"
              onClick={onApplyHint}
            >
              Switch to {hint.subject}
            </Button>
          </div>
        ) : !hint ? (
          <p className="text-xs text-muted-foreground">
            Attach a chapter below and we will fill these in for you — or pick
            them now.
          </p>
        ) : null}

        <div>
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Subject
          </p>
          <div
            className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-4"
            role="radiogroup"
            aria-label="Subject"
          >
            {SUBJECTS.map((s) => {
              const active = activeSubject === s;
              return (
                <button
                  key={s}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  // Re-choosing the lit tile must not flatten a board
                  // template's "English Language & Literature" to "English".
                  onClick={() => !active && onSubjectChange(s)}
                  className={cn(
                    "group relative flex min-w-0 items-center gap-2.5 overflow-hidden border p-2 pl-2.5 text-left text-sm font-medium",
                    "transition-[transform,box-shadow,border-color,background-color] duration-300 ease-[var(--ease)]",
                    "hover:-translate-y-0.5 hover:border-primary/60 hover:shadow-md hover:shadow-primary/10",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
                    active
                      ? "border-primary bg-primary/[0.06] text-primary"
                      : "border-border bg-card",
                  )}
                >
                  <span
                    aria-hidden
                    className={cn(
                      "absolute inset-y-0 left-0 w-0.5 origin-top bg-primary transition-transform duration-300 ease-[var(--ease)]",
                      active ? "scale-y-100" : "scale-y-0 group-hover:scale-y-100",
                    )}
                  />
                  <span
                    className={cn(
                      "flex size-8 shrink-0 items-center justify-center transition-colors duration-300",
                      active
                        ? "bg-primary text-primary-foreground"
                        : "bg-muted text-muted-foreground group-hover:bg-primary group-hover:text-primary-foreground",
                    )}
                  >
                    {React.createElement(SUBJECT_ICONS[s], { className: "size-4" })}
                  </span>
                  <span className="truncate">{s}</span>
                </button>
              );
            })}
          </div>
        </div>

        <ChoiceGroup
          label="Class"
          value={academicClass}
          onChange={onClassChange}
          options={CLASSES.map((c) => ({ value: c, label: c }))}
          chipClassName="min-w-11"
        />

        <div className="flex flex-wrap gap-x-8 gap-y-5">
          <ChoiceGroup
            label="Difficulty"
            value={difficulty}
            onChange={onDifficultyChange}
            options={DIFFICULTIES.map((d) => ({
              value: d,
              label: (
                <>
                  <span
                    className={cn(
                      "size-1.5 shrink-0 rounded-full",
                      d === difficulty ? "bg-primary-foreground" : DIFFICULTY_DOTS[d],
                    )}
                  />
                  <span className="capitalize">{d}</span>
                </>
              ),
            }))}
          />
          <ChoiceGroup
            label="Sets"
            value={numberOfSets}
            onChange={onSetsChange}
            options={SET_OPTIONS}
          />
          {/* Standard (041) and Basic (241) share the identical A–E skeleton
              and differ only in cognitive-band target, so this is a
              selection-time flag rather than a structural choice. Shown only
              where it means anything. */}
          {isMaths ? (
            <ChoiceGroup
              label="Maths level"
              value={mathLevel}
              onChange={onMathLevelChange}
              options={[
                { value: "standard", label: "Standard" },
                { value: "basic", label: "Basic" },
              ]}
            />
          ) : null}
        </div>
      </div>
    </section>
  );
}
