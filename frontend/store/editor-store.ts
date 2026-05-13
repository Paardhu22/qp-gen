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
  
  appendQuestions: (questions: Question[]) => void;
  clearQuestionsToAppend: () => void;
  
  setQuestionsToSave: (questions: Question[]) => void;
  setSaveModalOpen: (isOpen: boolean) => void;
}

export const useEditorStore = create<EditorState>((set) => ({
  questionsToAppend: [],
  questionsToSave: [],
  saveModalOpen: false,

  appendQuestions: (questions) => set((state) => ({ questionsToAppend: [...state.questionsToAppend, ...questions] })),
  clearQuestionsToAppend: () => set({ questionsToAppend: [] }),
  
  setQuestionsToSave: (questions) => set({ questionsToSave: questions }),
  setSaveModalOpen: (isOpen) => set({ saveModalOpen: isOpen }),
}));
