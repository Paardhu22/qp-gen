"use client";

import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Typography from "@tiptap/extension-typography";
import Placeholder from "@tiptap/extension-placeholder";
import Underline from "@tiptap/extension-underline";
import TextAlign from "@tiptap/extension-text-align";
import ImageResize from "tiptap-extension-resize-image";
import { Table } from "@tiptap/extension-table";
import { TableRow } from "@tiptap/extension-table-row";
import { TableCell } from "@tiptap/extension-table-cell";
import { TableHeader } from "@tiptap/extension-table-header";
import Superscript from "@tiptap/extension-superscript";
import Subscript from "@tiptap/extension-subscript";
import Highlight from "@tiptap/extension-highlight";
import Color from "@tiptap/extension-color";
import { TextStyle } from "@tiptap/extension-text-style";
import FontFamily from "@tiptap/extension-font-family";
import CharacterCount from "@tiptap/extension-character-count";
import Focus from "@tiptap/extension-focus";
import Dropcursor from "@tiptap/extension-dropcursor";
import Gapcursor from "@tiptap/extension-gapcursor";
import HardBreak from "@tiptap/extension-hard-break";

import {
  QuestionBlock,
  SectionBlock,
  InstructionBlock,
  QuestionGroupBlock,
  PageBreak,
} from "./editor/extensions/nodes";
import { PaperHeaderBlock as PaperHeaderBlockExt } from "./editor/extensions/header-node";
import { MathBlock, InlineMath } from "./editor/extensions/math-nodes";
import { DrawingBlock } from "./editor/extensions/drawing-node";
import { FloatImage } from "./editor/extensions/float-image";
import { PaginatedDocument } from "./editor/extensions/document-node";
import { PageNode } from "./editor/extensions/page-node";
import { PaginationEngine } from "./editor/extensions/pagination-engine";
import { FontSize } from "./editor/extensions/font-size";
import { LineHeight } from "./editor/extensions/line-height";
import { Indent as IndentExtension } from "./editor/extensions/indent";
import { EditorToolbar } from "./editor/toolbar";
import { FindReplace } from "./editor/find-replace";
import {
  createPageId,
  wrapHtmlInPage,
  ensurePageDocument,
  extractPagesFromDoc,
} from "./editor/pagination-utils";

import { useEditorStore } from "@/store/editor-store";
import { useEffect, useState, useMemo, useRef, memo } from "react";
import debounce from "lodash.debounce";
import { saveDraft, getDraft } from "@/lib/autosave-db";
import { toast } from "sonner";
import { useSession } from "@/lib/auth-client";

// ==================================
// Auto-numbering utility
// ==================================
function updateQuestionNumbers(editor: any) {
  if (!editor) return;
  let currentNumber = 1;
  const tr = editor.state.tr;

  editor.state.doc.descendants((node: any, pos: number) => {
    if (node.type.name === "questionBlock") {
      if (node.attrs.number !== currentNumber) {
        tr.setNodeMarkup(pos, undefined, {
          ...node.attrs,
          number: currentNumber,
        });
      }
      currentNumber++;
    }
  });

  if (tr.docChanged) {
    editor.view.dispatch(tr);
  }
}

type SectionSummary = {
  pos: number;
  title: string;
  questionCount: number;
  totalMarks: number;
  marksEach: number | null;
};

function buildSectionSummaryText(section: SectionSummary) {
  if (section.questionCount === 0) return "";
  if (section.marksEach !== null) {
    return `${section.questionCount} x ${section.marksEach} = ${section.totalMarks} Marks`;
  }
  return `${section.questionCount} Questions = ${section.totalMarks} Marks`;
}

function buildInstructionLine(section: SectionSummary) {
  if (section.questionCount === 0) {
    return `${section.title} has no questions.`;
  }
  if (section.marksEach !== null) {
    const markLabel = section.marksEach === 1 ? "mark" : "marks";
    return `${section.title} has ${section.questionCount} questions carrying ${section.marksEach} ${markLabel} each.`;
  }
  return `${section.title} has ${section.questionCount} questions carrying a total of ${section.totalMarks} marks.`;
}

function updateSectionSummaries(editor: any) {
  if (!editor) return;

  const { doc } = editor.state;
  const tr = editor.state.tr;
  const sections: SectionSummary[] = [];
  let currentSection: SectionSummary | null = null;
  let currentMarks: Set<number> = new Set();

  doc.descendants((node: any, pos: number) => {
    if (node.type.name === "sectionBlock") {
      const sec = currentSection;
      if (sec) {
        const marksEach = currentMarks.size === 1 ? [...currentMarks][0] : null;
        sections.push({
          ...(sec as SectionSummary),
          marksEach,
        });
      }

      currentSection = {
        pos,
        title: (node.textContent || "Section").trim(),
        questionCount: 0,
        totalMarks: 0,
        marksEach: null,
      };
      currentMarks = new Set();
      return;
    }

    if (node.type.name === "questionBlock" && currentSection) {
      const marks = Number(node.attrs?.marks ?? 0) || 0;
      currentSection.questionCount += 1;
      currentSection.totalMarks += marks;
      if (marks > 0) currentMarks.add(marks);
    }
  });

  const finalSec = currentSection;
  if (finalSec) {
    const marksEach = currentMarks.size === 1 ? [...currentMarks][0] : null;
    sections.push({
      ...(finalSec as SectionSummary),
      marksEach,
    });
  }

  sections.forEach((section) => {
    const node = doc.nodeAt(section.pos);
    if (!node) return;

    const summaryText = buildSectionSummaryText(section);
    const nextAttrs = {
      ...node.attrs,
      questionCount: section.questionCount,
      totalMarks: section.totalMarks,
      marksEach: section.marksEach,
      summaryText,
    };

    const hasChanged =
      node.attrs.questionCount !== nextAttrs.questionCount ||
      node.attrs.totalMarks !== nextAttrs.totalMarks ||
      node.attrs.marksEach !== nextAttrs.marksEach ||
      node.attrs.summaryText !== nextAttrs.summaryText;

    if (hasChanged) {
      tr.setNodeMarkup(section.pos, undefined, nextAttrs);
    }
  });

  const instructionLines =
    sections.length > 0
      ? [
          `This question paper has ${sections.length} section${
            sections.length === 1 ? "" : "s"
          }.`,
          ...sections.map((section) => buildInstructionLine(section)),
        ]
      : [];

  doc.descendants((node: any, pos: number) => {
    if (node.type.name !== "instructionBlock") return;
    if (node.attrs?.variant !== "general") return;

    const currentItems = node.attrs?.summaryItems || [];
    const isSame =
      Array.isArray(currentItems) &&
      currentItems.length === instructionLines.length &&
      currentItems.every(
        (item: string, index: number) => item === instructionLines[index],
      );

    if (!isSame) {
      tr.setNodeMarkup(pos, undefined, {
        ...node.attrs,
        summaryItems: instructionLines,
      });
    }
  });

  if (tr.docChanged) {
    editor.view.dispatch(tr);
  }
}

// ==================================
// Word count status bar
// ==================================
import {
  Cloud,
  CloudOff,
  CloudLightning,
  RefreshCw,
  CheckCircle2,
} from "lucide-react";

const StatusBar = memo(({ editor }: { editor: any }) => {
  if (!editor) return null;

  const chars = editor.storage.characterCount?.characters() || 0;
  const words = editor.storage.characterCount?.words() || 0;
  const saveState = useEditorStore((state) => state.saveState);

  const getSaveStateLabel = () => {
    switch (saveState) {
      case "saving":
        return (
          <span className="flex items-center gap-1 text-amber-600 dark:text-amber-400 font-medium animate-pulse">
            <RefreshCw className="h-3 w-3 animate-spin" /> Saving...
          </span>
        );
      case "saved":
        return (
          <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-medium">
            <Cloud className="h-3 w-3" /> Saved locally
          </span>
        );
      case "unsaved":
        return (
          <span className="flex items-center gap-1 text-zinc-400 dark:text-zinc-500 font-medium">
            <CheckCircle2 className="h-3 w-3 text-zinc-300" /> Unsaved changes
          </span>
        );
      case "offline":
        return (
          <span className="flex items-center gap-1 text-orange-600 dark:text-orange-400 font-medium animate-pulse">
            <CloudOff className="h-3 w-3" /> Offline (draft saved)
          </span>
        );
      case "failed":
        return (
          <span className="flex items-center gap-1 text-red-600 dark:text-red-400 font-medium animate-shake">
            <CloudLightning className="h-3 w-3" /> Sync failed
          </span>
        );
      default:
        return null;
    }
  };

  return (
    <div className="flex items-center justify-between px-4 py-1.5 bg-zinc-50 dark:bg-zinc-950 border-t border-zinc-200 dark:border-zinc-800 text-[10px] text-zinc-500 select-none flex-shrink-0">
      <div className="flex items-center gap-4">
        <span>Words: {words}</span>
        <span>Characters: {chars}</span>
      </div>
      <div className="flex items-center gap-4 font-mono">
        {getSaveStateLabel()}
        <span className="text-zinc-200 dark:text-zinc-850">|</span>
        <span>A4 | Portrait</span>
        <span>100%</span>
      </div>
    </div>
  );
});
StatusBar.displayName = "StatusBar";

// ==================================
// Default content for new papers
// ==================================
function createEmptyDocument() {
  return {
    type: "doc",
    content: [
      {
        type: "page",
        attrs: { pageId: createPageId() },
        content: [
          // ── Paper header ────────────────────────────────────────────────
          // Pre-filled with placeholder text so new documents always have a
          // professional title block at the top.  The user can edit or delete it.
          {
            type: "paperHeaderBlock",
            attrs: { logoUrl: null },
            content: [
              {
                type: "heading",
                attrs: { level: 1 },
                content: [{ type: "text", text: "SCHOOL / INSTITUTION NAME" }],
              },
              {
                type: "heading",
                attrs: { level: 2 },
                content: [{ type: "text", text: "SUBJECT — QUESTION PAPER" }],
              },
              {
                type: "paragraph",
                content: [
                  { type: "text", text: "Class —  |  Academic Year 20__–26" },
                ],
              },
              {
                type: "table",
                content: [
                  {
                    type: "tableRow",
                    content: [
                      {
                        type: "tableCell",
                        attrs: {},
                        content: [
                          {
                            type: "paragraph",
                            content: [
                              {
                                type: "text",
                                text: "Time Allowed: __ Hours",
                              },
                            ],
                          },
                        ],
                      },
                      {
                        type: "tableCell",
                        attrs: {},
                        content: [
                          {
                            type: "paragraph",
                            content: [
                              { type: "text", text: "Maximum Marks: __" },
                            ],
                          },
                        ],
                      },
                    ],
                  },
                ],
              },
            ],
          },
          // ── Body starts here ─────────────────────────────────────────────
          { type: "paragraph" },
        ],
      },
    ],
  };
}

function normalizeInitialContent(rawContent: string | undefined) {
  if (rawContent === undefined) return createEmptyDocument();

  const trimmed = rawContent.trim();
  if (!trimmed) return createEmptyDocument();

  try {
    const parsed = JSON.parse(trimmed);
    if (parsed && parsed.type === "doc") {
      return ensurePageDocument(parsed);
    }
  } catch {
    // Fall through to HTML handling.
  }

  return wrapHtmlInPage(trimmed);
}

function getLastPageInsertPos(editor: any) {
  const { doc } = editor.state;
  let lastPage: any = null;

  doc.descendants((node: any, pos: number) => {
    if (node.type.name === "page") {
      lastPage = { node, pos };
    }
  });

  if (!lastPage) return doc.content.size;
  return lastPage.pos + lastPage.node.nodeSize - 1;
}

function scrollToDocumentPosition(editor: any, position: number) {
  if (typeof window === "undefined") return;

  window.requestAnimationFrame(() => {
    try {
      const domAtPos = editor.view.domAtPos(Math.max(position + 1, 1));
      const node = domAtPos.node;
      const element = node instanceof HTMLElement ? node : node.parentElement;

      element?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    } catch {
      editor.view.dom.scrollIntoView({
        behavior: "smooth",
        block: "end",
      });
    }
  });
}

// ==================================
// Main Editor Component
// ==================================
type TiptapEditorProps = {
  initialContent?: string;
};

export const TiptapEditor = ({ initialContent }: TiptapEditorProps) => {
  const [isClient, setIsClient] = useState(false);
  const template = useEditorStore((state) => state.template);
  const { data: sessionData } = useSession();
  const userIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (sessionData?.user?.id) {
      userIdRef.current = sessionData.user.id;
    }
  }, [sessionData]);

  useEffect(() => {
    setIsClient(true);
  }, []);

  const debouncedNumbering = useMemo(
    () =>
      debounce((editor: any) => {
        updateQuestionNumbers(editor);
      }, 800),
    [],
  );

  const setPages = useEditorStore((state) => state.setPages);
  const debouncedPageState = useMemo(
    () =>
      debounce((editor: any) => {
        setPages(extractPagesFromDoc(editor.state.doc));
      }, 250),
    [setPages],
  );

  const debouncedSectionSummaries = useMemo(
    () =>
      debounce((editor: any) => {
        updateSectionSummaries(editor);
      }, 400),
    [],
  );

  const setSaveState = useEditorStore((state) => state.setSaveState);

  const debouncedAutosave = useMemo(
    () =>
      debounce(async (editor: any) => {
        if (!editor || editor.isDestroyed) return;
        setSaveState("saving");

        try {
          const editorJSON = editor.getJSON();
          const sections: any[] = [];
          const questions: any[] = [];

          editor.state.doc.descendants((node: any) => {
            if (node.type.name === "sectionBlock") {
              sections.push({
                title: (node.textContent || "").trim(),
                attrs: node.attrs,
              });
            } else if (node.type.name === "questionBlock") {
              let text = "";
              node.descendants((child: any) => {
                if (child.isText) text += child.text;
              });
              questions.push({
                content: text.trim() || (node.textContent || "").trim(),
                marks: node.attrs?.marks || 1,
                type: node.attrs?.questionType || "SHORT",
              });
            }
          });

          const currentUserId = userIdRef.current;
          if (!currentUserId) return; // Do not save drafts before the user session is resolved

          const isOnline =
            typeof navigator !== "undefined" ? navigator.onLine : true;
          const currentPaperId =
            typeof window !== "undefined"
              ? new URLSearchParams(window.location.search).get("paperId")
              : null;

          const draftId = currentPaperId
            ? `draft_${currentPaperId}_${currentUserId}`
            : `draft_new_${currentUserId}`;

          const draft = {
            id: draftId,
            paperId: currentPaperId,
            title: "Autosaved Draft",
            template,
            editorJSON,
            structuredData: {
              metadata: {
                title: "Autosaved Draft",
                template,
                updatedAt: Date.now(),
              },
              sections,
              questions,
            },
            updatedAt: Date.now(),
          };

          await saveDraft(draft);
          setSaveState(isOnline ? "saved" : "offline");
        } catch (error) {
          console.error("Autosave error:", error);
          setSaveState("failed");
        }
      }, 1500),
    [template, setSaveState],
  );

  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      PaginatedDocument,
      PageNode,
      PaginationEngine,
      StarterKit.configure({
        document: false,
        heading: {
          levels: [1, 2, 3, 4, 5, 6],
        },
        dropcursor: false,
        gapcursor: false,
        hardBreak: false,
        underline: false,
      }),
      Typography,
      Underline,
      Superscript,
      Subscript,
      Highlight.configure({
        multicolor: true,
      }),
      TextStyle,
      Color,
      FontFamily,
      FontSize,
      LineHeight,
      IndentExtension,
      TextAlign.configure({
        types: [
          "heading",
          "paragraph",
          "questionBlock",
          "sectionBlock",
          "instructionBlock",
        ],
      }),
      // ImageResize extends @tiptap/extension-image — do NOT also register
      // the base Image extension, or the two will conflict on the 'image' node name.
      ImageResize.configure({
        inline: true,
        allowBase64: true,
      }),
      // Block-level draggable image with resize + alignment controls
      FloatImage,
      Placeholder.configure({
        placeholder: "Start writing your exam paper...",
      }),
      Table.configure({
        resizable: true,
        allowTableNodeSelection: true,
      }),
      TableRow,
      TableHeader,
      TableCell,
      // Custom exam nodes
      QuestionBlock,
      SectionBlock,
      InstructionBlock,
      QuestionGroupBlock,
      PaperHeaderBlockExt,
      MathBlock,
      InlineMath,
      DrawingBlock,
      PageBreak,
      // Utilities
      CharacterCount,
      Focus.configure({
        className: "has-focus",
        mode: "deepest",
      }),
      Dropcursor.configure({
        color: "#000000",
        width: 2,
      }),
      Gapcursor,
      HardBreak,
    ],
    content: createEmptyDocument(),
    editorProps: {
      attributes: {
        id: "tiptap-paper-container",
        class: "document-editor focus:outline-none text-black",
        "data-template": template,
        spellcheck: "true",
      },
    },
    onUpdate: ({ editor }) => {
      setSaveState("unsaved");
      debouncedNumbering(editor);
      debouncedPageState(editor);
      debouncedSectionSummaries(editor);
      debouncedAutosave(editor);
    },
  });

  useEffect(() => {
    if (!editor) return;
    editor.setOptions({
      editorProps: {
        attributes: {
          id: "tiptap-paper-container",
          class: "document-editor focus:outline-none text-black",
          "data-template": template,
          spellcheck: "true",
        },
      },
    });
  }, [editor, template]);

  // Session Recovery & Local Offline detection
  useEffect(() => {
    if (!editor || editor.isDestroyed) return;

    const checkDraft = async () => {
      try {
        const currentUserId = userIdRef.current;
        if (!currentUserId) return; // Wait until session resolves

        const currentPaperId = new URLSearchParams(window.location.search).get(
          "paperId",
        );

        const draftId = currentPaperId
          ? `draft_${currentPaperId}_${currentUserId}`
          : `draft_new_${currentUserId}`;

        const draft = await getDraft(draftId);
        if (!draft) return;

        // Verify if this local draft belongs to the current editor session/paper context
        if (draft.paperId === currentPaperId) {
          const localTime = new Date(draft.updatedAt).toLocaleTimeString();
          
          toast.custom((t) => (
            <div className="bg-card text-foreground border border-border rounded-xl p-4 shadow-xl flex items-center justify-between gap-4 w-[350px]">
              <div className="flex flex-col gap-1 min-w-0">
                <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-indigo-500 animate-pulse" />
                  Unsaved draft found
                </span>
                <span className="text-[11px] text-muted-foreground truncate">
                  Created at {localTime}
                </span>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                <button
                  onClick={() => {
                    editor.commands.setContent(draft.editorJSON);
                    setPages(extractPagesFromDoc(editor.state.doc));
                    updateQuestionNumbers(editor);
                    updateSectionSummaries(editor);
                    setSaveState("saved");
                    toast.dismiss(t);
                    toast.success("Draft restored successfully!");
                  }}
                  className="bg-indigo-600 hover:bg-indigo-700 text-white text-[11.5px] font-bold px-3 py-1.5 rounded-lg shadow-sm transition-all"
                >
                  Restore
                </button>
                <button
                  onClick={() => toast.dismiss(t)}
                  className="text-muted-foreground hover:text-foreground text-[12px] font-bold hover:bg-muted/80 p-1.5 rounded-lg transition-all"
                >
                  ✕
                </button>
              </div>
            </div>
          ), { duration: 15000 });
        }
      } catch (err) {
        console.error("Failed to check draft recovery:", err);
      }
    };

    const timer = setTimeout(checkDraft, 1000);
    return () => clearTimeout(timer);
  }, [editor, setPages, setSaveState, sessionData]);

  useEffect(() => {
    const handleOnline = () => {
      const state = useEditorStore.getState().saveState;
      if (state === "offline") {
        setSaveState("saved");
      }
    };
    const handleOffline = () => {
      setSaveState("offline");
    };

    if (typeof window !== "undefined") {
      window.addEventListener("online", handleOnline);
      window.addEventListener("offline", handleOffline);
    }

    return () => {
      if (typeof window !== "undefined") {
        window.removeEventListener("online", handleOnline);
        window.removeEventListener("offline", handleOffline);
      }
    };
  }, [setSaveState]);

  useEffect(() => {
    return () => {
      debouncedNumbering.cancel();
      debouncedPageState.cancel();
      debouncedSectionSummaries.cancel();
      debouncedAutosave.cancel();
    };
  }, [
    debouncedNumbering,
    debouncedPageState,
    debouncedSectionSummaries,
    debouncedAutosave,
  ]);

  // Handle question insertion from AI generator
  const questionsToAppend = useEditorStore((state) => state.questionsToAppend);
  const clearQuestionsToAppend = useEditorStore(
    (state) => state.clearQuestionsToAppend,
  );
  const sectionsToAppend = useEditorStore((state) => state.sectionsToAppend);
  const clearSectionsToAppend = useEditorStore(
    (state) => state.clearSectionsToAppend,
  );

  const lastLoadedContentRef = useRef<string | null>(null);

  useEffect(() => {
    if (!editor) return;
    if (initialContent === undefined) return;
    if (lastLoadedContentRef.current === initialContent) return;

    // Mark as loaded immediately so a rapid re-render doesn't fire this twice.
    const content = initialContent ?? "";
    lastLoadedContentRef.current = content;
    const normalizedContent = normalizeInitialContent(content);

    queueMicrotask(() => {
      editor.commands.setContent(normalizedContent, { emitUpdate: false });
      setPages(extractPagesFromDoc(editor.state.doc));
      updateSectionSummaries(editor);
    });
  }, [editor, initialContent, setPages]);

  useEffect(() => {
    if (questionsToAppend.length === 0 || !editor) return;

    const questions = [...questionsToAppend];
    clearQuestionsToAppend();

    const contentToInsert: any[] = [];
    questions.forEach((q) => {
      const questionContent: any[] = [
        {
          type: "paragraph",
          content: [{ type: "text", text: q.content }],
        },
      ];

      if (q.type !== "TF" && q.options && q.options.length > 0) {
        questionContent.push({
          type: "orderedList",
          content: q.options.map((opt: string) => ({
            type: "listItem",
            content: [
              {
                type: "paragraph",
                content: [{ type: "text", text: opt }],
              },
            ],
          })),
        });
      }

      contentToInsert.push({
        type: "questionBlock",
        attrs: {
          marks: q.marks || 1,
          questionType:
            q.type || (q.options && q.options.length > 0 ? "MCQ" : "SHORT"),
        },
        content: questionContent,
      });
    });

    queueMicrotask(() => {
      if (editor.isDestroyed) return;

      const insertPosition = getLastPageInsertPos(editor);
      editor.commands.insertContentAt(insertPosition, contentToInsert);
      editor.commands.focus("end");
      scrollToDocumentPosition(editor, insertPosition);
    });
  }, [questionsToAppend, editor, clearQuestionsToAppend]);

  // Handle section-wise insertion from AI generator
  useEffect(() => {
    if (sectionsToAppend.length === 0 || !editor) return;

    const sections = [...sectionsToAppend];
    clearSectionsToAppend();

    const contentToInsert: any[] = [];
    sections.forEach((section) => {
      // Insert section header block
      contentToInsert.push({
        type: "sectionBlock",
        content: [{ type: "text", text: section.title }],
      });

      // Insert each question in this section
      section.questions.forEach((q) => {
        const questionContent: any[] = [
          {
            type: "paragraph",
            content: [{ type: "text", text: q.content }],
          },
        ];

        if (q.type !== "TF" && q.options && q.options.length > 0) {
          questionContent.push({
            type: "orderedList",
            content: q.options.map((opt: string) => ({
              type: "listItem",
              content: [
                {
                  type: "paragraph",
                  content: [{ type: "text", text: opt }],
                },
              ],
            })),
          });
        }

        contentToInsert.push({
          type: "questionBlock",
          attrs: {
            marks: q.marks || 1,
            questionType:
              q.type || (q.options && q.options.length > 0 ? "MCQ" : "SHORT"),
          },
          content: questionContent,
        });
      });
    });

    queueMicrotask(() => {
      if (editor.isDestroyed) return;

      const insertPosition = getLastPageInsertPos(editor);
      editor.commands.insertContentAt(insertPosition, contentToInsert);
      editor.commands.focus("end");
      scrollToDocumentPosition(editor, insertPosition);
    });
  }, [sectionsToAppend, editor, clearSectionsToAppend]);

  // Find/Replace state
  const [showFindReplace, setShowFindReplace] = useState(false);

  if (!isClient) return null;

  return (
    <div className="flex-1 flex flex-col h-full bg-white overflow-hidden">
      {editor && (
        <EditorToolbar
          editor={editor}
          onFindReplace={() => setShowFindReplace((v) => !v)}
        />
      )}
      {editor && showFindReplace && (
        <FindReplace
          editor={editor}
          onClose={() => setShowFindReplace(false)}
        />
      )}
      <div className="flex-1 overflow-y-auto custom-scrollbar bg-white print:p-0">
        <EditorContent editor={editor} className="h-full pb-32" />
      </div>
      {editor && <StatusBar editor={editor} />}

      <style
        dangerouslySetInnerHTML={{
          __html: `
        /* ===== Document Layout ===== */
        .document-editor {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 24px;
          padding: 28px 0 96px;
          background: #ffffff;
          color: #000000;
          font-family: "Times New Roman", Times, serif;
          font-size: 12pt;
          line-height: 1.35;
        }

        .document-editor .doc-page {
          width: 794px;
          min-height: 1123px;
          height: 1123px;
          background: #ffffff;
          border: 1px solid #000000;
          overflow: hidden;
          box-sizing: border-box;
        }

        .document-editor .doc-page-inner {
          height: 100%;
          display: flex;
          flex-direction: column;
        }

        .document-editor .doc-page-content {
          flex: 1;
          padding: 48px 56px 56px;
          box-sizing: border-box;
          min-height: 0;
          height: 100%;
          overflow: hidden;
        }

        .document-editor .doc-page-header,
        .document-editor .doc-page-footer {
          flex-shrink: 0;
          min-height: 0;
        }

        .document-editor img,
        .ProseMirror img {
          max-width: 100%;
          height: auto;
        }

        .ProseMirror p img,
        .ProseMirror li img {
          display: inline-block;
          vertical-align: middle;
          max-height: 220px;
        }

        .ProseMirror {
          color: #000000 !important;
          caret-color: #000000 !important;
          padding: 0 !important;
          min-height: 0;
          background: transparent !important;
        }

        .ProseMirror p {
          margin: 0 0 6px;
        }

        .ProseMirror h1,
        .ProseMirror h2,
        .ProseMirror h3,
        .ProseMirror h4 {
          margin: 0 0 6px;
          font-weight: 700;
        }

        .ProseMirror h1 {
          font-size: 16pt;
        }

        .ProseMirror h2 {
          font-size: 13pt;
        }

        .ProseMirror h3 {
          font-size: 12pt;
        }

        /* ===== Paper Header ===== */
        .paper-header-block {
          margin-bottom: 8px;
        }

        .paper-header-shell {
          display: grid;
          grid-template-columns: 96px 1fr 24px;
          column-gap: 12px;
          align-items: start;
        }

        .paper-header-logo-area {
          width: 88px;
          height: 88px;
          border: 1px solid #000000;
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
        }

        .paper-header-logo-area.is-empty {
          border: 1px solid #000000;
          color: #000000;
        }

        .logo-placeholder {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 4px;
          color: #000000;
        }

        .logo-remove-btn {
          border: 1px solid #000000;
          border-radius: 999px;
          padding: 2px;
          background: #ffffff;
          opacity: 0;
          transition: opacity 0.2s ease;
        }

        .paper-header-logo-area.has-logo:hover .logo-remove-btn {
          opacity: 1;
        }

        .paper-header-content {
          text-align: center;
        }

        .paper-header-content h1 {
          font-size: 16pt;
          font-weight: 700;
          text-transform: uppercase;
          margin: 0 0 4px;
        }

        .paper-header-content h2 {
          font-size: 13pt;
          font-weight: 700;
          text-transform: uppercase;
          margin: 0 0 4px;
        }

        .paper-header-content h3 {
          font-size: 12pt;
          font-weight: 700;
          text-transform: uppercase;
          margin: 0 0 4px;
        }

        .paper-header-content p {
          margin: 2px 0;
          font-size: 11pt;
        }

        .paper-header-block table {
          width: 100%;
          border-collapse: collapse;
          margin-top: 6px;
          border: none !important;
        }

        .paper-header-block td,
        .paper-header-block th {
          border: none !important;
          padding: 2px 0;
          font-size: 11pt;
        }

        .paper-header-block td:last-child,
        .paper-header-block th:last-child {
          text-align: right;
        }

        .paper-header-delete {
          border: 1px solid #000000;
          background: #ffffff;
          color: #000000;
          border-radius: 999px;
          padding: 2px;
          opacity: 0;
          transition: opacity 0.2s ease;
          height: 20px;
          width: 20px;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .paper-header-block:hover .paper-header-delete {
          opacity: 1;
        }

        /* ===== Section Block ===== */
        .section-block {
          position: relative;
          margin: 10px 0 6px;
          break-inside: avoid;
          page-break-inside: avoid;
        }

        .section-header {
          display: flex;
          justify-content: space-between;
          align-items: baseline;
          border-top: 1px solid #000000;
          border-bottom: 1px solid #000000;
          padding: 4px 0;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          font-size: 10pt;
        }

        .section-title {
          flex: 1;
        }

        .section-summary {
          text-transform: none;
          letter-spacing: 0;
          font-size: 10pt;
        }

        .section-instructions {
          margin-top: 4px;
          font-size: 10pt;
        }

        .section-table-header {
          display: grid;
          grid-template-columns: 56px 1fr 56px;
          border: 1px solid #000000;
          background: #ffffff;
          margin: 4px 0;
          break-inside: avoid;
          page-break-inside: avoid;
        }

        .section-table-cell {
          padding: 5px 6px;
          font-size: 10pt;
          font-weight: 700;
          text-transform: uppercase;
          text-align: center;
        }

        .section-table-cell + .section-table-cell {
          border-left: 1px solid #000000;
        }

        .section-table-cell:nth-child(2) {
          text-align: left;
        }

        .section-controls {
          position: absolute;
          right: -6px;
          top: -6px;
          opacity: 0;
          transition: opacity 0.2s ease;
        }

        .section-block:hover .section-controls {
          opacity: 1;
        }

        .section-delete {
          border: 1px solid #000000;
          background: #ffffff;
          color: #000000;
          border-radius: 999px;
          padding: 2px;
          height: 20px;
          width: 20px;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        /* ===== Question Block ===== */
        .question-block {
          position: relative;
          margin: 4px 0;
          break-inside: avoid;
          page-break-inside: avoid;
        }

        .question-row {
          display: grid;
          grid-template-columns: 56px 1fr 56px;
          border: 1px solid #000000;
          break-inside: avoid;
          page-break-inside: avoid;
        }

        .question-cell {
          padding: 6px 8px;
        }

        .question-cell + .question-cell {
          border-left: 1px solid #000000;
        }

        .question-no {
          text-align: center;
          font-weight: 700;
          white-space: nowrap;
        }

        .question-body {
          line-height: 1.35;
        }

        .question-marks {
          text-align: center;
          white-space: nowrap;
        }

        .question-marks-input {
          width: 24px;
          border: none;
          text-align: center;
          font-family: inherit;
          font-size: 11pt;
          background: transparent;
          padding: 0;
          margin: 0;
          outline: none;
          color: #000000;
        }

        .question-marks-label {
          font-size: 10pt;
          margin-left: 2px;
        }

        .question-controls {
          position: absolute;
          right: -6px;
          top: 4px;
          opacity: 0;
          transition: opacity 0.2s ease;
        }

        .question-block:hover .question-controls {
          opacity: 1;
        }

        .question-delete {
          border: 1px solid #000000;
          background: #ffffff;
          color: #000000;
          border-radius: 999px;
          padding: 2px;
          height: 20px;
          width: 20px;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        /* ===== MCQ Options ===== */
        .question-body ul,
        .question-body ol {
          margin: 4px 0 0;
          padding: 0;
          list-style: none;
          counter-reset: option;
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
          column-gap: 12px;
          row-gap: 2px;
        }

        .question-body ul li,
        .question-body ol li {
          display: flex;
          gap: 6px;
          min-width: 0;
        }

        .question-body ul li::before,
        .question-body ol li::before {
          counter-increment: option;
          content: "(" counter(option, upper-alpha) ") ";
          font-weight: 700;
          flex-shrink: 0;
        }

        .question-body ul li p,
        .question-body ol li p {
          margin: 0;
        }

        /* ===== Instruction Block ===== */
        .instruction-block {
          position: relative;
          margin: 10px 0;
          padding: 8px 10px;
          border: 1px solid #000000;
          background: #ffffff;
          break-inside: avoid;
          page-break-inside: avoid;
        }

        .instruction-header {
          font-weight: 700;
          text-transform: uppercase;
          font-size: 10pt;
          margin-bottom: 4px;
        }

        .instruction-list {
          margin: 0 0 4px 18px;
          padding: 0;
        }

        .instruction-content p {
          margin: 0 0 4px;
        }

        .instruction-controls {
          position: absolute;
          right: -6px;
          top: -6px;
          opacity: 0;
          transition: opacity 0.2s ease;
        }

        .instruction-block:hover .instruction-controls {
          opacity: 1;
        }

        .instruction-delete {
          border: 1px solid #000000;
          background: #ffffff;
          color: #000000;
          border-radius: 999px;
          padding: 2px;
          height: 20px;
          width: 20px;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        /* ===== Question Group (OR) ===== */
        .question-group {
          position: relative;
          margin: 8px 0;
          padding: 6px 0;
          border-top: 1px solid #000000;
          border-bottom: 1px solid #000000;
          background: #ffffff;
          break-inside: avoid;
          page-break-inside: avoid;
        }

        .question-group-label {
          text-align: center;
          font-weight: 700;
          font-size: 10pt;
          letter-spacing: 0.08em;
          text-transform: uppercase;
        }

        .question-group-content {
          margin-top: 6px;
        }

        .question-group-controls {
          position: absolute;
          right: -6px;
          top: -6px;
          opacity: 0;
          transition: opacity 0.2s ease;
        }

        .question-group:hover .question-group-controls {
          opacity: 1;
        }

        .question-group-delete {
          border: 1px solid #000000;
          background: #ffffff;
          color: #000000;
          border-radius: 999px;
          padding: 2px;
          height: 20px;
          width: 20px;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        /* ===== Math ===== */
        .math-block {
          border: 1px solid #000000;
          margin: 6px 0;
          padding: 6px;
          text-align: center;
          background: #ffffff;
          break-inside: avoid;
          page-break-inside: avoid;
        }

        .math-block-display {
          cursor: pointer;
        }

        .math-block-empty {
          color: #000000;
          font-style: italic;
        }

        .math-block-editor {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }

        .math-block-input {
          width: 100%;
          border: 1px solid #000000;
          padding: 4px;
          font-family: "Courier New", monospace;
          font-size: 10pt;
          resize: vertical;
          min-height: 60px;
          outline: none;
        }

        .math-block-hint {
          font-size: 9pt;
          color: #000000;
          text-align: left;
        }

        .inline-math {
          display: inline-block;
          margin: 0 2px;
        }

        .inline-math-display {
          cursor: pointer;
          border-bottom: 1px dotted #000000;
          padding: 0 2px;
        }

        .inline-math-empty {
          color: #000000;
          font-style: italic;
        }

        .inline-math-editor {
          display: inline-flex;
          align-items: center;
          border: 1px solid #000000;
          padding: 0 2px;
          background: #ffffff;
        }

        .inline-math-input {
          border: none;
          outline: none;
          font-family: "Courier New", monospace;
          font-size: 10pt;
          width: 100px;
          background: transparent;
        }

        /* ===== Drawing Block ===== */
        .drawing-block {
          position: relative;
          border: 1px solid #000000;
          padding: 6px;
          margin: 6px 0;
          background: #ffffff;
          break-inside: avoid;
          page-break-inside: avoid;
        }

        .drawing-toolbar {
          display: flex;
          align-items: center;
          gap: 6px;
          border-bottom: 1px solid #000000;
          padding-bottom: 6px;
          margin-bottom: 6px;
        }

        .drawing-tool {
          border: 1px solid #000000;
          background: #ffffff;
          padding: 2px;
          border-radius: 2px;
        }

        .drawing-tool.is-active {
          background: #000000;
          color: #ffffff;
        }

        .drawing-divider {
          width: 1px;
          height: 16px;
          background: #000000;
        }

        .drawing-color {
          width: 24px;
          height: 24px;
          padding: 0;
          border: 1px solid #000000;
          background: #ffffff;
        }

        .drawing-clear {
          margin-left: auto;
          font-size: 9pt;
          color: #000000;
        }

        .drawing-canvas {
          display: flex;
          justify-content: center;
          border: 1px solid #000000;
          background: #ffffff;
        }

        .drawing-surface {
          cursor: crosshair;
          background: #ffffff;
        }

        .drawing-delete {
          border: 1px solid #000000;
          background: #ffffff;
          color: #000000;
          border-radius: 999px;
          padding: 2px;
          height: 20px;
          width: 20px;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        /* ===== Float Image Block ===== */
        .float-image-wrapper {
          margin: 8px 0;
          break-inside: avoid;
          page-break-inside: avoid;
        }

        .float-image-img {
          display: block;
          width: 100%;
          height: auto;
          border: 1px solid #000000;
        }

        /* Alignment + delete toolbar — sits above the image */
        .float-image-controls {
          position: absolute;
          top: -28px;
          left: 50%;
          transform: translateX(-50%);
          display: flex;
          align-items: center;
          gap: 2px;
          padding: 3px 5px;
          background: #ffffff;
          border: 1px solid #000000;
          opacity: 0;
          transition: opacity 0.15s;
          z-index: 20;
          white-space: nowrap;
          pointer-events: none;
        }

        .float-image-wrapper:hover .float-image-controls,
        .float-image-container.is-selected .float-image-controls {
          opacity: 1;
          pointer-events: auto;
        }

        .float-img-btn {
          border: 1px solid #000000;
          background: #ffffff;
          color: #000000;
          padding: 2px;
          border-radius: 2px;
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          height: 18px;
          width: 18px;
        }

        .float-img-btn.active {
          background: #000000;
          color: #ffffff;
        }

        .float-img-divider {
          display: inline-block;
          width: 1px;
          height: 14px;
          background: #000000;
          flex-shrink: 0;
          align-self: center;
          margin: 0 2px;
        }

        /* Resize handle — bottom-right corner triangle */
        .float-image-resize-handle {
          position: absolute;
          bottom: 0;
          right: 0;
          width: 0;
          height: 0;
          border-style: solid;
          border-width: 0 0 14px 14px;
          border-color: transparent transparent #000000 transparent;
          cursor: nwse-resize;
          opacity: 0;
          transition: opacity 0.15s;
        }

        .float-image-wrapper:hover .float-image-resize-handle,
        .float-image-container.is-selected .float-image-resize-handle,
        .float-image-container.is-resizing .float-image-resize-handle {
          opacity: 1;
        }

        /* ===== Page Break ===== */
        .ProseMirror [data-type="page-break"] {
          display: none !important;
          page-break-after: always;
          break-after: page;
        }

        /* ===== Focus Styles ===== */
        .has-focus {
          outline: 1px solid #000000;
          outline-offset: 0;
          box-shadow: none;
        }

        /* ===== Table Styles ===== */
        .ProseMirror table {
          border-collapse: separate;
          border-spacing: 0;
          width: 100%;
          margin: 8px 0;
          break-inside: avoid;
          page-break-inside: avoid;
        }

        .ProseMirror table td,
        .ProseMirror table th {
          border-top: 1px solid #000000;
          border-right: 1px solid #000000;
          border-bottom: 0;
          border-left: 0;
          padding: 4px 6px;
          vertical-align: top;
          break-inside: avoid;
          page-break-inside: avoid;
        }

        .ProseMirror table th {
          font-weight: 700;
          background: #ffffff;
        }

        .ProseMirror table tr td:first-child,
        .ProseMirror table tr th:first-child {
          border-left: 1px solid #000000;
        }

        .ProseMirror table {
          border-bottom: 1px solid #000000;
        }

        .ProseMirror table tr {
          break-inside: avoid;
          page-break-inside: avoid;
        }

        /* ===== List Styles ===== */
        .ProseMirror ul,
        .ProseMirror ol {
          margin: 0 0 6px 18px;
          padding: 0;
        }

        .ProseMirror ul ul,
        .ProseMirror ol ol {
          margin-bottom: 0;
        }

        /* ===== Placeholder ===== */
        .ProseMirror .is-editor-empty:first-child::before {
          content: attr(data-placeholder);
          float: left;
          color: #000000;
          pointer-events: none;
          height: 0;
          font-style: italic;
        }

        /* ===== Horizontal Rule ===== */
        .ProseMirror hr {
          border: none;
          border-top: 1px solid #000000;
          margin: 10px 0;
        }

        /* ===== Print Styles ===== */
        @media print {
          @page {
            size: A4;
            margin: 12mm;
          }

          body * {
            visibility: hidden;
          }

          #tiptap-paper-container,
          #tiptap-paper-container * {
            visibility: visible;
          }

          #tiptap-paper-container {
            position: static;
            width: 100%;
            margin: 0 !important;
            padding: 0 !important;
            color: #000000 !important;
            background: #ffffff !important;
            border: none !important;
            box-shadow: none !important;
            max-width: none !important;
          }

          .document-editor {
            gap: 0;
            padding: 0;
            background: #ffffff;
          }

          .doc-page {
            width: 210mm;
            min-height: 297mm;
            height: 297mm;
            margin: 0 !important;
            border: none !important;
            box-shadow: none !important;
            overflow: visible !important;
            page-break-after: always;
            break-after: page;
          }

          .doc-page-content {
            padding: 15mm 16mm !important;
            min-height: auto !important;
            height: auto !important;
            overflow: visible !important;
          }

          .question-controls,
          .section-controls,
          .instruction-controls,
          .question-group-controls,
          .paper-header-delete,
          .logo-remove-btn,
          .drawing-delete,
          .float-image-hide-in-pdf {
            display: none !important;
          }

          .paper-header-logo-area.is-empty {
            display: none;
          }

          #tiptap-paper-container [data-type="page-break"] {
            display: none !important;
          }

          .custom-scrollbar {
            overflow: visible !important;
          }
        }
      `,
        }}
      />
    </div>
  );
};

export const DocumentEditor = TiptapEditor;
