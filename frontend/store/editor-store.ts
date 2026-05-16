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

  appendQuestions: (questions: Question[]) => void;
  clearQuestionsToAppend: () => void;

  appendSections: (sections: SectionToAppend[]) => void;
  clearSectionsToAppend: () => void;

  setQuestionsToSave: (questions: Question[]) => void;
  setSaveModalOpen: (isOpen: boolean) => void;
  setEditorContent: (content: string) => void;
}

export const useEditorStore = create<EditorState>((set) => ({
  questionsToAppend: [],
  sectionsToAppend: [],
  questionsToSave: [],
  saveModalOpen: false,

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

  setQuestionsToSave: (questions) => set({ questionsToSave: questions }),
  setSaveModalOpen: (isOpen) => set({ saveModalOpen: isOpen }),
}));
