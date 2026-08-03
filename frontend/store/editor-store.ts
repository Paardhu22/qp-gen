import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

export interface Question {
  content: string;
  answer?: string;
  options?: string[];
  type: string;
  marks: number;
  image_url?: string;
}

export interface SectionToAppend {
  title: string;
  questions: Question[];
  /**
   * Optional set label ("A" | "B" | "C"). When present, the editor scopes the
   * section-header dedupe by set and renders the header as "Set B · Section A"
   * so questions from different sets can coexist in ONE document without
   * merging under a shared "Section A" header. Absent (single-set / review-tray
   * path) → today's exact behaviour is preserved.
   */
  setLabel?: string;
}

export interface UploadedDoc {
  id: string;
  name: string;
  size: number;
}

export interface AppliedHsatSource {
  id: string;
  grade: string;
  subject: string;
  book: string;
  status: "not_ingested" | "pending" | "processing" | "ready" | "error";
  chunkCount: number;
  selectedChapterCount?: number;
}

/**
 * A staged generated question awaiting the teacher's decision.
 *
 * `id` is a stable client-generated id (random per question) so multi-select
 * and per-question insert/dismiss can target it. `sourceType` carries the
 * provenance from the generator (`rag` = grounded in uploaded chunks,
 * `curriculum_fallback` = generated from CBSE curriculum because the slot
 * was uncovered). It surfaces in the review tray badge so the teacher can
 * choose to drop ungrounded questions.
 */
export interface TrayItem {
  id: string;
  sectionTitle: string;
  question: Question & {
    metadata?: Record<string, any>;
    bloom?: string;
    or_choice?: any;
    vi_alternative?: string;
  };
  /**
   * Provenance of the question, used to badge it in the review tray.
   *
   * - "pool"            — written by Model 1 from the chapter
   * - "chapter_figure"  — written about a figure extracted from the chapter
   * - "synthetic_image" — uses an AI-drawn diagram; needs a teacher's eye
   * - "rag" / "curriculum_fallback" — provenance from the pre-pool engine,
   *   still present on questions saved before the refactor
   */
  sourceType:
    | "pool"
    | "chapter_figure"
    | "synthetic_image"
    | "rag"
    | "curriculum_fallback"
    | "unknown";
  /** Local timestamp (ms) the item entered the tray. */
  addedAt: number;
  /** Set true once the teacher inserts it; remains in the tray as "Inserted ✓" until cleared. */
  inserted: boolean;
}

export type InsertionMode = "review" | "auto";

/**
 * One blueprint slot, placed on the page before its question exists.
 *
 * The whole shape of a paper is known as soon as the blueprint compiles — the
 * sections, how many questions, what each is worth — while the questions
 * themselves take minutes to write. Placing the empty paper first turns the
 * wait into a document filling in rather than a page growing from nothing.
 */
export interface GhostSlot {
  /** Blueprint index. The fill finds its slot by this, never by position. */
  index: number;
  sectionTitle: string;
  marks: number;
  questionType: string;
}

/** A written question, destined for the ghost holding its slot. */
export interface SlotFill {
  index: number;
  sectionTitle: string;
  question: Question & { metadata?: Record<string, any> };
}

/**
 * One produced paper set (A / B / C) held for the Comparison Workspace.
 * `result` is the assembled-paper payload the SSE pipeline emits
 * (`{ sections, generalInstructions, meta }`) — the same shape the generator
 * preview and `handleAddToEditor` already consume.
 */
export interface ComparisonSet {
  label: string;
  result: any;
}

/**
 * Set labels reach the store in two shapes — the pipeline emits bare "A"/"B",
 * saved `PaperSet` rows and some older call sites carry "Set A". The editor's
 * tab state is always the bare letter, so anything used as a key into
 * `approvedSets` has to be normalised or the lookup silently misses and the
 * tab falls back to its IndexedDB draft — i.e. the previous paper.
 */
export function normalizeSetLabel(label: string): string {
  return label.replace(/^Set\s+/i, "").trim() || label;
}

export type SaveState = "saving" | "saved" | "offline" | "failed";

/**
 * The generation currently in flight, if any.
 *
 * This lives in the store rather than in the component that started it. A run
 * takes minutes, and the surface that kicked it off — the editor page, the
 * dashboard — unmounts the moment the teacher looks at something else. When
 * the progress lived in that component's `useState`, walking to the dashboard
 * and back produced a Paper Studio that looked idle while the stream was still
 * running underneath, because the remount started from the initial state.
 *
 * Only the light, durable facts belong here: it is persisted to localStorage,
 * so the assembled paper (which is large) stays in `lib/generation-runner.ts`
 * module memory and reaches the editor through `comparisonSets` as before.
 *
 * `paperId` is what makes an insert safe. A run belongs to the paper it was
 * started for, and questions must never land in whatever document happens to
 * be mounted when they arrive.
 */
export interface ActiveRun {
  runId: string;
  /** The paper this run was started for. Null for a draft with no id yet. */
  paperId: string | null;
  /** Where it was started, so the tracker can route back to the right screen. */
  origin: "editor" | "dashboard";
  startedAt: number;
  /** Last human-readable line from the pipeline. */
  phase: string;
  /** Questions received so far. */
  produced: number;
  /** Questions the blueprint planned, once known. 0 until the `plan` event. */
  total: number;
  /** True for a run producing more than one set. */
  multiSet: boolean;
}

/**
 * One-shot request for the TipTap editor to remove a question node from
 * the live document. We compare on section title + content text since
 * the tray stores the source-of-truth Question payload, not editor pos.
 */
export interface QuestionRemovalRequest {
  /** Random token so React effect dependency re-fires per request. */
  token: string;
  sectionTitle: string;
  content: string;
}

interface EditorState {
  // ── Insertion plumbing into the TipTap editor ─────────────────────
  questionsToAppend: Question[];
  sectionsToAppend: SectionToAppend[];
  instructionsToAppend: string[] | null;
  questionsToSave: Question[];
  /** Pending tray-driven "Undo" removals, consumed by tiptap-editor. */
  questionRemovals: QuestionRemovalRequest[];
  /** Blueprint slots waiting to be laid out as placeholders. */
  ghostSlotsToPlace: GhostSlot[];
  /** Written questions waiting to replace the placeholder holding their slot. */
  slotFills: SlotFill[];
  /**
   * One-shot request to remove every placeholder still unfilled.
   *
   * A run that is cancelled or fails leaves ghosts for the questions that were
   * never written. Left alone they are permanent empty numbered questions in
   * the teacher's paper, so the end of every run sweeps them. A token rather
   * than a boolean so consecutive runs each re-fire the effect.
   */
  pendingSweepToken: string | null;

  // ── Modal state ───────────────────────────────────────────────────
  savePaperModalOpen: boolean;
  saveQuestionModalOpen: boolean;
  questionBankBrowserOpen: boolean;

  // ── Editor mirror (kept for backwards-compat callers) ─────────────
  editorContent: string;
  pages: Array<{ id: string; blocks: any[] }>;
  template: string;
  saveState: SaveState;

  // ── Generator + tray + session context ────────────────────────────
  /** "review" (default): generated questions land in the tray; teacher
   *  decides what to insert. "auto": old behaviour — every generated
   *  question is auto-inserted into the editor while streaming. */
  insertionMode: InsertionMode;
  /** Issue 3 — text typed in the generator form's "General Instructions"
   *  textarea. Persisted so a page reload, account switch back, or
   *  return-from-editor doesn't lose what the teacher wrote. */
  generalInstructionsDraft: string;
  /** Paper settings handed over by the dashboard assistant.
   *
   *  The assistant gathers requirements conversationally, then routes here.
   *  The generator form consumes this ONCE on mount and clears it, so the
   *  handoff cannot re-apply itself every time the teacher returns to the
   *  editor and silently undo whatever they changed by hand. Passed through
   *  the store rather than the URL because it is a small object, and a query
   *  string would put a half-specified paper in the browser history. */
  paperSpecHandoff: Record<string, any> | null;
  /** Staging area for generated questions awaiting review. */
  generatedTray: TrayItem[];
  /** All produced sets (A + derived B/C) from the latest multi-set generation.
   *  Drives the Comparison Workspace. Empty = no multi-set result to compare. */
  comparisonSets: ComparisonSet[];
  /** The ID of the paper that the current comparisonSets belong to. 
   *  Used to prevent unapproved sets from bleeding when opening a different paper. */
  comparisonSetsPaperId: string | null;
  /** The ID of the paper currently loaded in the editor, used to stamp new comparisonSets. */
  activeEditorPaperId: string | null;
  /** Whether the full-screen Comparison Workspace overlay is open. */
  comparisonOpen: boolean;
  /** The generation in flight, or null. Survives navigation; see `ActiveRun`. */
  activeRun: ActiveRun | null;
  /**
   * Whether the Paper Studio dock is expanded. Persisted because it is part of
   * the workspace the teacher arranged, not transient UI — collapsing it,
   * checking the dashboard and coming back to a re-expanded panel is the same
   * class of annoyance as losing the run itself.
   */
  studioDockOpen: boolean;
  /** Unsent text in the Studio dock's brief field. Persisted for the same reason. */
  studioBrief: string;
  /** Persisted user uploads for the current generation session */
  uploadedDocs: UploadedDoc[];
  /** Persisted library sources for the current generation session */
  hsatSources: AppliedHsatSource[];
  /**
   * Sets the teacher has approved, keyed by label ("A" | "B" | "C").
   *
   * Approval is what puts a generated paper into its editor tab. The review
   * workspace no longer inserts anything: it reviews, replaces and approves,
   * and each approved set becomes the initial content of its own tab. Empty
   * until the teacher approves.
   */
  approvedSets: Record<string, any>;
  /**
   * Bumped on every approval. The editor folds this into its content-load key
   * so a second generation replaces the tab's document instead of losing to
   * the IndexedDB draft written by the first one.
   */
  approvedAt: number;
  /**
   * Set when a paper generated OUTSIDE the editor (the dashboard) is handed
   * over, cleared the first time the editor mounts and takes it.
   *
   * The editor's resume flow runs whenever it opens with no `?paperId=`, which
   * is exactly how the dashboard arrives. It would either silently redirect to
   * the previous draft or pop "Resume previous paper?" over the paper the
   * teacher just waited minutes for. A fresh generation is the thing to show —
   * there is nothing to resume.
   */
  awaitingGeneratedPaper: boolean;
  /** Last metadata picked up from the generator form / loaded paper.
   *  Used to make the resume modal truthful and prefill Paper Details. */
  generatorContext: {
    examName: string;
    className: string;
    subject: string;
    /** Last time the user actively touched the editor (ms epoch). */
    lastActiveAt: number;
  };

  // ── Actions ───────────────────────────────────────────────────────
  appendQuestions: (questions: Question[]) => void;
  clearQuestionsToAppend: () => void;

  appendSections: (sections: SectionToAppend[]) => void;
  clearSectionsToAppend: () => void;

  appendInstructions: (instructions: string[]) => void;
  clearInstructionsToAppend: () => void;

  setQuestionsToSave: (questions: Question[]) => void;
  setSavePaperModalOpen: (isOpen: boolean) => void;
  setSaveQuestionModalOpen: (isOpen: boolean) => void;
  setQuestionBankBrowserOpen: (isOpen: boolean) => void;
  setEditorContent: (content: string) => void;
  setPages: (pages: Array<{ id: string; blocks: any[] }>) => void;
  setTemplate: (template: string) => void;
  setSaveState: (state: SaveState) => void;

  setInsertionMode: (mode: InsertionMode) => void;
  setGeneralInstructionsDraft: (draft: string) => void;
  setPaperSpecHandoff: (spec: Record<string, any> | null) => void;
  setGeneratorContext: (
    ctx: Partial<EditorState["generatorContext"]>,
  ) => void;
  pushToTray: (
    item: Omit<TrayItem, "id" | "addedAt" | "inserted"> & {
      id?: string;
      addedAt?: number;
    },
  ) => void;
  removeFromTray: (id: string) => void;
  markTrayInserted: (ids: string[]) => void;
  markTrayUninserted: (ids: string[]) => void;
  removeSectionFromEditor: (req: Omit<QuestionRemovalRequest, "token">) => void;
  consumeQuestionRemovals: () => void;
  clearTray: () => void;

  placeGhostSlots: (slots: GhostSlot[]) => void;
  clearGhostSlots: () => void;
  fillSlot: (fill: SlotFill) => void;
  clearSlotFills: () => void;
  /** Ask the editor to drop every still-pending placeholder. */
  sweepPendingSlots: () => void;
  consumePendingSweep: () => void;

  setComparisonSets: (sets: ComparisonSet[]) => void;
  clearComparisonSets: () => void;
  setComparisonOpen: (open: boolean) => void;
  replaceComparisonQuestion: (
    label: string,
    slotIndex: number,
    question: any,
  ) => void;
  removeComparisonQuestion: (label: string, slotIndex: number) => void;
  approveComparisonSets: () => void;
  /** Put an already-generated paper straight into the editor tabs, approved.
   *  For generations that happen outside the review workspace (the dashboard). */
  adoptGeneratedSets: (sets: ComparisonSet[]) => void;
  /** One-shot: the editor calls this on mount to take the pending handoff. */
  consumeGeneratedPaperHandoff: () => void;
  clearApprovedSets: () => void;

  setActiveEditorPaperId: (paperId: string | null) => void;

  /** Register a run as in flight. Called by the runner, not by a component. */
  startRun: (run: ActiveRun) => void;
  /** Merge progress into the live run. A no-op once the run has ended. */
  updateRun: (patch: Partial<Omit<ActiveRun, "runId">>) => void;
  /** Clear the run — on completion, failure or cancellation alike. */
  endRun: () => void;

  setStudioDockOpen: (open: boolean) => void;
  setStudioBrief: (brief: string) => void;

  setUploadedDocs: (docs: UploadedDoc[] | ((prev: UploadedDoc[]) => UploadedDoc[])) => void;
  setHsatSources: (sources: AppliedHsatSource[] | ((prev: AppliedHsatSource[]) => AppliedHsatSource[])) => void;
}

/**
 * Walk a set's `result.sections`, applying `mutate` to the question at
 * `slotIndex`. Returning `null` from `mutate` deletes the question.
 *
 * Kept structural rather than mutating in place: the sets are React state, so
 * every level that changes has to be a new object or the editor tabs (which
 * read `result` as their initial content) will not see the update.
 */
function mapSetQuestion(
  set: ComparisonSet,
  slotIndex: number,
  mutate: (question: any) => any | null,
): ComparisonSet {
  const sections = (set.result?.sections || []).map((section: any) => {
    const questions: any[] = [];
    let touched = false;
    (section.questions || []).forEach((q: any, position: number) => {
      const key = Number(q?.metadata?.slotIndex);
      const resolved = Number.isFinite(key) ? key : position;
      if (resolved !== slotIndex) {
        questions.push(q);
        return;
      }
      touched = true;
      const next = mutate(q);
      if (next) questions.push(next);
    });
    return touched ? { ...section, questions } : section;
  });

  const totalQuestions = sections.reduce(
    (n: number, s: any) => n + (s.questions?.length || 0),
    0,
  );
  const totalMarks = sections.reduce(
    (n: number, s: any) =>
      n +
      (s.questions || []).reduce(
        (m: number, q: any) => m + (Number(q.marks) || 0),
        0,
      ),
    0,
  );

  return {
    ...set,
    result: {
      ...set.result,
      sections,
      meta: { ...(set.result?.meta || {}), totalQuestions, totalMarks },
    },
  };
}

const initialGeneratorContext: EditorState["generatorContext"] = {
  examName: "",
  className: "",
  subject: "",
  lastActiveAt: 0,
};

export const useEditorStore = create<EditorState>()(
  persist(
    (set) => ({
      // ── Insertion plumbing ─────────────────────────────────────────
      questionsToAppend: [],
      sectionsToAppend: [],
      instructionsToAppend: null,
      questionsToSave: [],
      questionRemovals: [],
      ghostSlotsToPlace: [],
      slotFills: [],
      pendingSweepToken: null,

      // ── Modals ──────────────────────────────────────────────────────
      savePaperModalOpen: false,
      saveQuestionModalOpen: false,
      questionBankBrowserOpen: false,

      // ── Editor mirror ───────────────────────────────────────────────
      editorContent: "",
      pages: [],
      template: "cbse",
      saveState: "saved",

      // ── Generator + tray + session context ──────────────────────────
      // Questions land on the page as they are written. The paper building
      // itself is the point of watching a generation, and staging every
      // question in a tray first meant the document stayed empty throughout
      // the one process the teacher was waiting on. The tray still exists and
      // is still reachable — it reviews what has been placed rather than
      // gating what may be placed.
      insertionMode: "auto",
      generatedTray: [],
      comparisonSets: [],
      comparisonSetsPaperId: null,
      activeEditorPaperId: null,
      comparisonOpen: false,
      activeRun: null,
      studioDockOpen: true,
      studioBrief: "",
      approvedSets: {},
      approvedAt: 0,
      awaitingGeneratedPaper: false,
      generatorContext: initialGeneratorContext,
      generalInstructionsDraft: "",
      paperSpecHandoff: null,
      uploadedDocs: [],
      hsatSources: [],

      // ── Actions ─────────────────────────────────────────────────────
      appendQuestions: (questions) =>
        set((state) => ({
          questionsToAppend: [...state.questionsToAppend, ...questions],
        })),
      clearQuestionsToAppend: () => set({ questionsToAppend: [] }),

      appendSections: (sections) =>
        set((state) => ({
          sectionsToAppend: [...state.sectionsToAppend, ...sections],
        })),
      clearSectionsToAppend: () => set({ sectionsToAppend: [] }),

      appendInstructions: (instructions) =>
        set({ instructionsToAppend: instructions }),
      clearInstructionsToAppend: () => set({ instructionsToAppend: null }),

      setEditorContent: (content) => set({ editorContent: content }),

      setPages: (pages) => set({ pages }),

      setTemplate: (template) => set({ template }),

      setQuestionsToSave: (questions) => set({ questionsToSave: questions }),
      setSavePaperModalOpen: (isOpen) => set({ savePaperModalOpen: isOpen }),
      setSaveQuestionModalOpen: (isOpen) =>
        set({ saveQuestionModalOpen: isOpen }),
      setQuestionBankBrowserOpen: (isOpen) =>
        set({ questionBankBrowserOpen: isOpen }),
      setSaveState: (saveState) => set({ saveState }),

      setInsertionMode: (mode) => set({ insertionMode: mode }),

      setGeneralInstructionsDraft: (draft) =>
        set({ generalInstructionsDraft: draft }),

      setPaperSpecHandoff: (spec) => set({ paperSpecHandoff: spec }),

      setGeneratorContext: (ctx) =>
        set((state) => ({
          generatorContext: { ...state.generatorContext, ...ctx },
        })),

      pushToTray: (item) =>
        set((state) => ({
          generatedTray: [
            ...state.generatedTray,
            {
              id: item.id || `tray-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
              sectionTitle: item.sectionTitle,
              question: item.question,
              sourceType: item.sourceType,
              addedAt: item.addedAt || Date.now(),
              inserted: false,
            },
          ],
        })),

      removeFromTray: (id) =>
        set((state) => ({
          generatedTray: state.generatedTray.filter((t) => t.id !== id),
        })),

      markTrayInserted: (ids) =>
        set((state) => ({
          generatedTray: state.generatedTray.map((t) =>
            ids.includes(t.id) ? { ...t, inserted: true } : t,
          ),
        })),

      markTrayUninserted: (ids) =>
        set((state) => ({
          generatedTray: state.generatedTray.map((t) =>
            ids.includes(t.id) ? { ...t, inserted: false } : t,
          ),
        })),

      removeSectionFromEditor: (req) =>
        set((state) => ({
          questionRemovals: [
            ...state.questionRemovals,
            {
              token: `rm-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
              sectionTitle: req.sectionTitle,
              content: req.content,
            },
          ],
        })),

      consumeQuestionRemovals: () => set({ questionRemovals: [] }),

      clearTray: () => set({ generatedTray: [] }),

      placeGhostSlots: (slots) => set({ ghostSlotsToPlace: slots }),
      clearGhostSlots: () => set({ ghostSlotsToPlace: [] }),

      // Queued rather than applied directly: the editor may not have finished
      // loading its document when a question lands, and the same guard that
      // protects `questionsToAppend` from draining into a blank page has to
      // protect fills too.
      fillSlot: (fill) =>
        set((state) => ({ slotFills: [...state.slotFills, fill] })),
      clearSlotFills: () => set({ slotFills: [] }),

      sweepPendingSlots: () =>
        set({
          pendingSweepToken: `sweep-${Date.now()}-${Math.random()
            .toString(36)
            .slice(2, 8)}`,
        }),
      consumePendingSweep: () => set({ pendingSweepToken: null }),

      setActiveEditorPaperId: (paperId) => set({ activeEditorPaperId: paperId }),

      startRun: (run) => set({ activeRun: run }),

      // Guarded on `runId`: a late event from a run that was cancelled or
      // superseded must not resurrect it. Without the check, aborting a run
      // and immediately starting another lets the first one's trailing events
      // overwrite the second one's progress.
      updateRun: (patch) =>
        set((state) =>
          state.activeRun
            ? { activeRun: { ...state.activeRun, ...patch } }
            : {},
        ),

      endRun: () => set({ activeRun: null }),

      setStudioDockOpen: (open) => set({ studioDockOpen: open }),
      setStudioBrief: (brief) => set({ studioBrief: brief }),

      setComparisonSets: (sets) => set((state) => ({ comparisonSets: sets, comparisonSetsPaperId: state.activeEditorPaperId })),
      clearComparisonSets: () =>
        set({
          comparisonSets: [],
          comparisonSetsPaperId: null,
          comparisonOpen: false,
          approvedSets: {},
          approvedAt: 0,
          awaitingGeneratedPaper: false,
        }),
      setComparisonOpen: (open) => set({ comparisonOpen: open }),

      replaceComparisonQuestion: (label, slotIndex, question) =>
        set((state) => ({
          comparisonSets: state.comparisonSets.map((s) =>
            s.label === label
              ? mapSetQuestion(s, slotIndex, (existing) => ({
                  ...existing,
                  ...question,
                  metadata: {
                    ...(existing?.metadata || {}),
                    ...(question?.metadata || {}),
                  },
                }))
              : s,
          ),
        })),

      removeComparisonQuestion: (label, slotIndex) =>
        set((state) => ({
          comparisonSets: state.comparisonSets.map((s) =>
            s.label === label ? mapSetQuestion(s, slotIndex, () => null) : s,
          ),
        })),

      // Approval is the ONLY path from the review workspace into the editor.
      // Each set's assembled paper becomes the initial content of its own tab,
      // which is why there is no per-question / per-section / per-set insert
      // any more — the tabs already exist, so inserting was busywork that also
      // let two sets collide in one document.
      approveComparisonSets: () =>
        set((state) => ({
          approvedSets: Object.fromEntries(
            state.comparisonSets.map((s) => [
              normalizeSetLabel(s.label),
              s.result,
            ]),
          ),
          approvedAt: Date.now(),
          comparisonOpen: false,
        })),

      // The dashboard runs the generation itself and then navigates to the
      // editor, so there is no review workspace in between for the teacher to
      // approve from. Without this the sets landed in `comparisonSets` and
      // stopped there: tab A reads `approvedSets` first and `comparisonSets`
      // only for tabs B/C, so Set A never reached the document, and because
      // nothing was approved the editor was free to rehydrate the tab's
      // IndexedDB draft — the PREVIOUS paper — over the top of the blank tab.
      // Worse, a single-set request never rendered the "Review & approve sets"
      // panel at all (it needs two sets to compare), so there was no way to
      // reach the paper the teacher had just waited minutes for.
      //
      // Generating from the dashboard is itself the "use this paper"
      // instruction, so it approves. The sets stay in `comparisonSets` so the
      // review workspace is still reachable afterwards for a multi-set run.
      adoptGeneratedSets: (sets) =>
        set((state) => ({
          comparisonSets: sets,
          comparisonSetsPaperId: state.activeEditorPaperId,
          approvedSets: Object.fromEntries(
            sets.map((s) => [normalizeSetLabel(s.label), s.result]),
          ),
          approvedAt: Date.now(),
          comparisonOpen: false,
          awaitingGeneratedPaper: true,
        })),

      consumeGeneratedPaperHandoff: () =>
        set({ awaitingGeneratedPaper: false }),

      clearApprovedSets: () => set({ approvedSets: {}, approvedAt: 0, awaitingGeneratedPaper: false }),

      setUploadedDocs: (docs) =>
        set((state) => ({
          uploadedDocs: typeof docs === "function" ? docs(state.uploadedDocs) : docs,
        })),
      
      setHsatSources: (sources) =>
        set((state) => ({
          hsatSources: typeof sources === "function" ? sources(state.hsatSources) : sources,
        })),
    }),
    {
      // The persistence key is namespaced so callers (auth signOut, account
      // switch) can wipe it deterministically via the helper below. The
      // localStorage key MUST match `EDITOR_STORE_PERSIST_KEY` exported below.
      name: "qp-gen-editor-store",
      storage: createJSONStorage(() => {
        if (typeof window === "undefined") {
          // SSR fallback — returns an empty store; not actually used.
          return {
            getItem: () => null,
            setItem: () => undefined,
            removeItem: () => undefined,
          };
        }
        return window.localStorage;
      }),
      // Persist only the slices that matter across route changes/reloads.
      // The large TipTap doc continues to live in IndexedDB via
      // `live-document-db.ts` (see tiptap-editor.tsx); persisting it twice
      // would blow past localStorage's ~5MB cap.
      partialize: (state) => ({
        insertionMode: state.insertionMode,
        generatedTray: state.generatedTray,
        // The produced sets (assembled papers, not the TipTap doc) survive
        // navigation so the Comparison Workspace can be reopened. `comparisonOpen`
        // is transient UI and deliberately NOT persisted.
        comparisonSets: state.comparisonSets,
        comparisonSetsPaperId: state.comparisonSetsPaperId,
        // Approved sets survive navigation so returning to the editor from
        // another route does not lose the paper the teacher just accepted.
        approvedSets: state.approvedSets,
        approvedAt: state.approvedAt,
        awaitingGeneratedPaper: state.awaitingGeneratedPaper,
        // The run in flight, so returning to the editor from another route
        // finds Paper Studio exactly as it was left. Small by design — the
        // assembled paper is not in here.
        activeRun: state.activeRun,
        studioDockOpen: state.studioDockOpen,
        studioBrief: state.studioBrief,
        generatorContext: state.generatorContext,
        template: state.template,
        generalInstructionsDraft: state.generalInstructionsDraft,
        // Persisted so the handoff survives the navigation from the dashboard
        // to the editor even if the tab reloads on the way.
        paperSpecHandoff: state.paperSpecHandoff,
      }),
      version: 2,
      /**
       * v1 → v2: questions are placed on the page as they are generated.
       *
       * `insertionMode` is persisted, so every teacher who has ever opened the
       * editor is carrying `"review"` in localStorage — the old default. Left
       * alone they would keep the old staging behaviour forever and never see
       * the paper build, which is the whole change.
       *
       * Rewriting it is safe precisely because nothing can set it: there is no
       * toggle anywhere in the UI, so a stored `"review"` is a stale default
       * rather than a decision anyone made. Introduce a control for it and
       * this migration has to become conditional on that control.
       */
      migrate: (persisted: any, version: number) => {
        if (version < 2 && persisted && persisted.insertionMode === "review") {
          return { ...persisted, insertionMode: "auto" };
        }
        return persisted;
      },
    },
  ),
);

// ---------------------------------------------------------------------------
// Account-switch hygiene (Cluster A.5).
//
// The Zustand store above persists the per-user `generatedTray` (and
// `generatorContext`) in localStorage. Without an explicit wipe on signOut,
// the next user signing in on the same browser inherits the previous user's
// review tray — questions they never generated, pre-flagged as "Inserted"
// because the persisted state remembered the prior user's insert action.
// Calling `resetEditorStoreForAccountSwitch()` from the auth-client's
// signOut/signIn flow eliminates the leak deterministically.
// ---------------------------------------------------------------------------

export const EDITOR_STORE_PERSIST_KEY = "qp-gen-editor-store";

export function resetEditorStoreForAccountSwitch(): void {
  // Reset in-memory state first so any subscriber that re-renders during the
  // wipe sees the clean shape rather than the soon-to-be-deleted persisted
  // copy. Then drop the persisted blob so a hard refresh stays clean.
  useEditorStore.setState({
    generatedTray: [],
    comparisonSets: [],
    comparisonSetsPaperId: null,
    comparisonOpen: false,
    activeRun: null,
    studioBrief: "",
    approvedSets: {},
    approvedAt: 0,
    awaitingGeneratedPaper: false,
    questionsToAppend: [],
    sectionsToAppend: [],
    instructionsToAppend: null,
    questionsToSave: [],
    questionRemovals: [],
    ghostSlotsToPlace: [],
    slotFills: [],
    pendingSweepToken: null,
    insertionMode: "auto",
    generatorContext: initialGeneratorContext,
    generalInstructionsDraft: "",
  });
  try {
    useEditorStore.persist?.clearStorage?.();
  } catch {
    // Older zustand persist middleware exposes only the storage option, no
    // helper. Fall back to a direct localStorage removal so the key is gone.
  }
  if (typeof window !== "undefined") {
    try {
      window.localStorage.removeItem(EDITOR_STORE_PERSIST_KEY);
    } catch {
      // Ignore — localStorage can throw in private-mode browsers.
    }
  }
}
