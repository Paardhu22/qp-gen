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
  /** "rag" | "curriculum_fallback" — see GenerationRouter docs. */
  sourceType: "rag" | "curriculum_fallback" | "unknown";
  /** Local timestamp (ms) the item entered the tray. */
  addedAt: number;
  /** Set true once the teacher inserts it; remains in the tray as "Inserted ✓" until cleared. */
  inserted: boolean;
}

export type InsertionMode = "review" | "auto";

export type SaveState = "saving" | "saved" | "offline" | "failed";

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
  /** Staging area for generated questions awaiting review. */
  generatedTray: TrayItem[];
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
      insertionMode: "review",
      generatedTray: [],
      generatorContext: initialGeneratorContext,
      generalInstructionsDraft: "",

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
        generatorContext: state.generatorContext,
        template: state.template,
        generalInstructionsDraft: state.generalInstructionsDraft,
      }),
      version: 1,
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
    questionsToAppend: [],
    sectionsToAppend: [],
    instructionsToAppend: null,
    questionsToSave: [],
    questionRemovals: [],
    insertionMode: "review",
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
