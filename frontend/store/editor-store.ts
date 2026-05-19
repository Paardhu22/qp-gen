import { create } from "zustand";

interface Question {
  content: string;
  answer?: string;
  options?: string[];
  type: string;
  marks: number;
}

export interface SectionToAppend {
  title: string;
  questions: Question[];
}

interface EditorState {
  questionsToAppend: Question[];
  sectionsToAppend: SectionToAppend[];
  questionsToSave: Question[];
  saveModalOpen: boolean;
  editorContent: string;
  pages: Array<{ id: string; blocks: any[] }>;
  template: string;
  saveState: "saving" | "saved" | "unsaved" | "offline" | "failed";

  appendQuestions: (questions: Question[]) => void;
  clearQuestionsToAppend: () => void;

  appendSections: (sections: SectionToAppend[]) => void;
  clearSectionsToAppend: () => void;

  setQuestionsToSave: (questions: Question[]) => void;
  setSaveModalOpen: (isOpen: boolean) => void;
  setEditorContent: (content: string) => void;
  setPages: (pages: Array<{ id: string; blocks: any[] }>) => void;
  setTemplate: (template: string) => void;
  setSaveState: (state: "saving" | "saved" | "unsaved" | "offline" | "failed") => void;
}

export const useEditorStore = create<EditorState>((set) => ({
  questionsToAppend: [],
  sectionsToAppend: [],
  questionsToSave: [],
  saveModalOpen: false,
  template: "cbse",
  saveState: "saved",

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

  editorContent: "",
  setEditorContent: (content) => set({ editorContent: content }),

  pages: [],
  setPages: (pages) => set({ pages }),

  setTemplate: (template) => set({ template }),

  setQuestionsToSave: (questions) => set({ questionsToSave: questions }),
  setSaveModalOpen: (isOpen) => set({ saveModalOpen: isOpen }),
  setSaveState: (saveState) => set({ saveState }),
}));
