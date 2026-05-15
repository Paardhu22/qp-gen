import { create } from "zustand";

interface Question {
  content: string;
  answer?: string;
  options?: string[];
  type: string;
  marks: number;
}

interface EditorState {
  questionsToAppend: Question[];
  questionsToSave: Question[];
  saveModalOpen: boolean;
  editorContent: string;

  appendQuestions: (questions: Question[]) => void;
  clearQuestionsToAppend: () => void;

  setQuestionsToSave: (questions: Question[]) => void;
  setSaveModalOpen: (isOpen: boolean) => void;
  setEditorContent: (content: string) => void;
}

export const useEditorStore = create<EditorState>((set) => ({
  questionsToAppend: [],
  questionsToSave: [],
  saveModalOpen: false,

  appendQuestions: (questions) =>
    set((state) => ({
      questionsToAppend: [...state.questionsToAppend, ...questions],
    })),
  clearQuestionsToAppend: () => set({ questionsToAppend: [] }),

  editorContent: "",
  setEditorContent: (content) => set({ editorContent: content }),

  setQuestionsToSave: (questions) => set({ questionsToSave: questions }),
  setSaveModalOpen: (isOpen) => set({ saveModalOpen: isOpen }),
}));
