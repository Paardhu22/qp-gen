"use client";

import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { OrderedList } from "@tiptap/extension-list";
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
  GroupedQuestionBlock,
} from "./editor/extensions/nodes";
import { PaperHeaderBlock as PaperHeaderBlockExt } from "./editor/extensions/header-node";
import { QuestionHoverMenu } from "./editor/question-hover-menu";
import { ImageStyleDialog } from "./editor/image-style-dialog";
import { useQuestionMenu } from "@/lib/use-question-menu";
import { OrGroupInvariant } from "./editor/extensions/or-group-invariant";
import { MathBlock, InlineMath } from "./editor/extensions/math-nodes";
// DrawingBlock intentionally removed — feature retired in this round.
import { FloatImage } from "./editor/extensions/float-image";
import { PaginatedDocument } from "./editor/extensions/document-node";
import { PageNode } from "./editor/extensions/page-node";
import { PaginationEngine } from "./editor/extensions/pagination-engine";
import { FontSize } from "./editor/extensions/font-size";
import { LineHeight } from "./editor/extensions/line-height";
import { Indent as IndentExtension } from "./editor/extensions/indent";
import { ReviewTray } from "./review-tray";
import { templates, defaultHeaderJSON } from "./editor/templates";
import { EditorToolbar } from "./editor/toolbar";
import { FindReplace } from "./editor/find-replace";
import {
  createPageId,
  wrapHtmlInPage,
  ensurePageDocument,
  extractPagesFromDoc,
} from "./editor/pagination-utils";
// Block mapping lives in one module so the three insertion paths (initial
// content for Sets B/C, live auto-insert, section insert) cannot drift apart.
import {
  buildInlineRun,
  buildQuestionBlocks,
  buildQuestionContentNodes,
} from "./editor/question-nodes";

import { isEnglishSubject } from "@/lib/subject";
import { useEditorStore } from "@/store/editor-store";
import { useEffect, useState, useMemo, useRef, memo } from "react";
import debounce from "lodash.debounce";
import {
  getLatestLiveDocumentForUser,
  getLiveDocument,
  getLiveDocumentId,
  saveLiveDocument,
  type LiveEditorDocument,
} from "@/lib/live-document-db";
import {
  backendSyncTarget,
  basePaperId,
  splitPaperId,
  withSetSuffix,
  persistablePaperId,
  DRAFT_PAPER_ID,
} from "@/lib/paper-id";
import { useSession } from "@/lib/auth-client";
import { updatePaperAction } from "@/actions/savePaper";
import { SyncCancelledError } from "@/lib/api-client";
import { type AppliedHsatSource } from "@/components/hsat-source-picker";

// ==================================
// Auto-numbering utility
// ==================================
function updateQuestionNumbers(editor: any) {
  if (!editor) return;
  let currentNumber = 1;
  const tr = editor.state.tr;
  const letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

  editor.state.doc.descendants((node: any, pos: number) => {
    // OR group occupies ONE question slot. Assign its number, then
    // walk its branches and stamp each with `subLabel = "<n>(A)"` /
    // "<n>(B)" so the QuestionBlock NodeView renders the OR-branch
    // format ("31(A)") instead of its standalone number. Anything
    // outside an OR group keeps subLabel === null.
    if (node.type.name === "questionGroupBlock") {
      const groupNumber = currentNumber;
      if (node.attrs.number !== groupNumber) {
        tr.setNodeMarkup(pos, undefined, { ...node.attrs, number: groupNumber });
      }
      let branchIndex = 0;
      let childOffset = pos + 1;
      node.forEach((child: any) => {
        if (
          child.type.name === "questionBlock" ||
          child.type.name === "groupedQuestionBlock"
        ) {
          const letter = letters[branchIndex] || `${branchIndex + 1}`;
          const desired = `${groupNumber}(${letter})`;
          if (child.attrs.subLabel !== desired) {
            tr.setNodeMarkup(childOffset, undefined, {
              ...child.attrs,
              subLabel: desired,
            });
          }
          branchIndex += 1;
        }
        childOffset += child.nodeSize;
      });
      currentNumber++;
      return false; // OR group is counted once; skip recursion.
    }

    if (
      node.type.name === "questionBlock" ||
      node.type.name === "groupedQuestionBlock"
    ) {
      const updates: Record<string, unknown> = {};
      if (node.attrs.number !== currentNumber) {
        updates.number = currentNumber;
      }
      // Drag-out from an OR group must drop the stale subLabel,
      // otherwise the standalone question keeps showing "31(A)".
      if (node.attrs.subLabel !== null) {
        updates.subLabel = null;
      }
      if (Object.keys(updates).length > 0) {
        tr.setNodeMarkup(pos, undefined, { ...node.attrs, ...updates });
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

    // OR group counts as ONE question slot; don't recurse into its children.
    if (node.type.name === "questionGroupBlock" && currentSection) {
      // Use the marks of the first question child (plain or grouped) as
      // representative — both branches carry equal marks by definition.
      let groupMarks = 0;
      node.forEach((child: any) => {
        if (
          groupMarks === 0 &&
          (child.type.name === "questionBlock" ||
            child.type.name === "groupedQuestionBlock")
        ) {
          groupMarks = Number(child.attrs?.marks ?? 0) || 0;
        }
      });
      currentSection.questionCount += 1;
      currentSection.totalMarks += groupMarks;
      if (groupMarks > 0) currentMarks.add(groupMarks);
      return false; // skip all children — OR group is ONE question slot
    }

    if (
      (node.type.name === "questionBlock" ||
        node.type.name === "groupedQuestionBlock") &&
      currentSection
    ) {
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
import { Cloud, CloudOff, CloudLightning, RefreshCw } from "lucide-react";

const StatusBar = memo(({ editor }: { editor: any }) => {
  const saveState = useEditorStore((state) => state.saveState);
  // PERF: character/word counts are O(doc-nodes). The old path re-read
  // them on every saveState flip (i.e. every keystroke) because saveState
  // toggled "saving" → "saved" each time. Cache locally and refresh on a
  // 500 ms debounced editor `update` instead.
  const [counts, setCounts] = useState<{ chars: number; words: number }>({
    chars: 0,
    words: 0,
  });
  useEffect(() => {
    if (!editor) return;
    const read = () => {
      try {
        const cc = editor.storage?.characterCount;
        if (!cc) return;
        setCounts({
          chars: cc.characters?.() || 0,
          words: cc.words?.() || 0,
        });
      } catch {
        /* characterCount not ready yet on first render */
      }
    };
    const debounced = debounce(read, 500);
    read();
    editor.on("update", debounced);
    return () => {
      editor.off("update", debounced);
      debounced.cancel();
    };
  }, [editor]);

  if (!editor) return null;
  const { chars, words } = counts;

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
            <Cloud className="h-3 w-3" /> Saved
          </span>
        );

      case "offline":
        return (
          <span className="flex items-center gap-1 text-orange-600 dark:text-orange-400 font-medium animate-pulse">
            <CloudOff className="h-3 w-3" /> Offline
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
    <div className="flex items-center justify-between px-4 py-1.5 bg-muted/20 border-t border-border text-[10px] text-muted-foreground select-none flex-shrink-0">
      <div className="flex items-center gap-4">
        <span>Words: {words}</span>
        <span>Characters: {chars}</span>
      </div>
      <div className="flex items-center gap-4 font-mono">
        {getSaveStateLabel()}
        <span className="text-border">|</span>
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
        content: [{ type: "paragraph" }],
      },
    ],
  };
}

export function normalizeInitialContent(rawContent: string | undefined) {
  if (rawContent === undefined) return createEmptyDocument();

  const trimmed = rawContent.trim();
  if (!trimmed) return createEmptyDocument();

  try {
    const parsed = JSON.parse(trimmed);
    if (parsed && parsed.type === "doc") {
      return ensurePageDocument(parsed);
    }
    if (parsed?.editorJSON?.type === "doc") {
      return ensurePageDocument(parsed.editorJSON);
    }
    if (parsed?.document?.type === "doc") {
      return ensurePageDocument(parsed.document);
    }
    
      // Convert raw generator result (e.g. Set B / C) into TipTap JSON directly
    if (parsed && Array.isArray(parsed.sections)) {
      const pageContent: any[] = [defaultHeaderJSON];
      parsed.sections.forEach((section: any) => {
        const title = String(section.title || "").trim();
        if (title) {
          pageContent.push({
            type: "sectionBlock",
            content: [{ type: "text", text: title }],
          });
        }
        (section.questions || []).forEach((q: any) => {
          pageContent.push(...buildQuestionBlocks(q));
        });
      });
      if (pageContent.length === 1) pageContent.push({ type: "paragraph" });
      return {
        type: "doc",
        content: [
          {
            type: "page",
            attrs: { pageId: createPageId() },
            content: pageContent,
          }
        ]
      };
    }
  } catch {
    // Fall through to HTML handling.
  }

  return wrapHtmlInPage(trimmed);
}

type PaperMetadata = {
  examName?: string;
  className?: string;
  subject?: string;
};

function resolvePaperMetadata(metadata?: PaperMetadata | null) {
  return {
    title: metadata?.examName?.trim() || "",
    className: metadata?.className?.trim() || "",
    subject: metadata?.subject?.trim() || "",
  };
}

function buildPersistedPaperContent(params: {
  editorJSON: any;
  pages: Array<{ id: string; blocks: any[] }>;
  template: string;
  metadata?: PaperMetadata | null;
  updatedAt: number;
}) {
  const metadata = resolvePaperMetadata(params.metadata);

  return {
    version: 1,
    editorJSON: params.editorJSON,
    pages: params.pages,
    metadata: {
      ...metadata,
      template: params.template,
      updatedAt: params.updatedAt,
    },
    layout: {
      pageSize: "A4" as const,
      orientation: "portrait" as const,
      template: params.template,
      pages: params.pages,
    },
    updatedAt: params.updatedAt,
  };
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
  paperId?: string | null;
  serverUpdatedAt?: string | null;
  paperMetadata?: PaperMetadata;
  hsatSources?: AppliedHsatSource[];
  uploadedDocs?: { id: string; name: string; size: number }[];
  onPaperCreatedAction?: (paperId: string) => void;
  exportType?: "question_paper" | "answer_script" | "question_bank";
  /**
   * Load `initialContent` even when an IndexedDB draft exists for this paper.
   *
   * The draft normally wins — that is what makes a reload keep your edits.
   * But an approved generation is an explicit "use this paper" instruction
   * from the teacher, and the tab it targets usually already holds a draft
   * from the PREVIOUS generation. Without this flag the second approval of a
   * given tab silently does nothing.
   */
  forceInitialContent?: boolean;
  /**
   * Changes whenever `initialContent` is authoritatively replaced (the
   * approval timestamp). Folded into the load key so the same JSON approved
   * twice still triggers a reload.
   */
  contentVersion?: number;
  /**
   * Panels flanking the page, rendered BELOW the toolbar and beside the
   * scrolling canvas — the layout every word processor uses.
   *
   * They are passed in rather than owned here because their state has to
   * outlive this component: the editor remounts on every set-tab switch (see
   * the `key` at the call site), and a panel that collapsed itself each time
   * the teacher changed tabs would be unusable. The page holds the open/closed
   * state; this only positions them.
   */
  leftPanel?: React.ReactNode;
  rightPanel?: React.ReactNode;
};

export const TiptapEditor = ({
  initialContent,
  paperId = null,
  serverUpdatedAt = null,
  paperMetadata,
  hsatSources,
  uploadedDocs,
  onPaperCreatedAction,
  exportType = "question_paper",
  forceInitialContent = false,
  contentVersion = 0,
  leftPanel,
  rightPanel,
}: TiptapEditorProps) => {
  const [isClient, setIsClient] = useState(false);
  const template = useEditorStore((state) => state.template);
  const { data: sessionData } = useSession();
  const userIdRef = useRef<string | null>(null);
  const paperIdRef = useRef<string | null>(paperId);
  const paperMetadataRef = useRef<PaperMetadata | undefined>(paperMetadata);
  const hsatSourcesRef = useRef<AppliedHsatSource[]>(hsatSources || []);
  const uploadedDocsRef = useRef<{ id: string; name: string; size: number }[]>(uploadedDocs || []);

  useEffect(() => {
    hsatSourcesRef.current = hsatSources || [];
  }, [hsatSources]);

  useEffect(() => {
    uploadedDocsRef.current = uploadedDocs || [];
  }, [uploadedDocs]);

  const onPaperCreatedRef =
    useRef<TiptapEditorProps["onPaperCreatedAction"]>(onPaperCreatedAction);
  const syncPromiseRef = useRef<Promise<void>>(Promise.resolve());
  // Holds the AbortController for the currently in-flight save/update HTTP
  // request.  Replaced on every sync so the previous request is cancelled when
  // a newer edit arrives.
  const syncAbortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (sessionData?.user?.id) {
      userIdRef.current = sessionData.user.id;
    }
  }, [sessionData]);

  // ── ISSUE 1: per-browser-session id so the resume modal can tell an
  // in-app navigation apart from a genuine "last time you were here"
  // resume. The id lives in sessionStorage (cleared when the tab closes)
  // and is stamped onto every IDB save below.
  const browserSessionIdRef = useRef<string>("");
  useEffect(() => {
    if (typeof window === "undefined") return;
    const KEY = "qp-gen:editor-session-id";
    let id = sessionStorage.getItem(KEY);
    if (!id) {
      id = `sess-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
      sessionStorage.setItem(KEY, id);
    }
    browserSessionIdRef.current = id;
  }, []);

  useEffect(() => {
    paperIdRef.current = paperId;
  }, [paperId]);

  useEffect(() => {
    paperMetadataRef.current = paperMetadata;
  }, [paperMetadata]);

  useEffect(() => {
    onPaperCreatedRef.current = onPaperCreatedAction;
  }, [onPaperCreatedAction]);

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
  const setEditorContent = useEditorStore((state) => state.setEditorContent);

  const debouncedLiveSync = useMemo(
    () =>
      debounce((editor: any) => {
        if (!editor || editor.isDestroyed) return;

        // Cancel any in-flight HTTP request from a previous sync — the new
        // edit supersedes it.  A fresh controller is created for this sync.
        syncAbortControllerRef.current?.abort();
        const syncAbortController = new AbortController();
        syncAbortControllerRef.current = syncAbortController;

        // ISSUE 1: capture editor state SYNCHRONOUSLY at debounce-fire
        // time, NOT inside the deferred .then() chain. Otherwise
        // `.flush()` on link-click queues a microtask that runs after
        // `editor.destroy()`, and `editor.getJSON()` throws (or returns
        // stale state). Capturing here means even an abrupt unmount
        // preserves the last edits.
        const currentUserIdSync = userIdRef.current;
        if (!currentUserIdSync) return;
        const updatedAt = new Date().getTime();
        const capturedJSON = editor.getJSON();
        const capturedPages = extractPagesFromDoc(editor.state.doc);
        const capturedContentPayload = buildPersistedPaperContent({
          editorJSON: capturedJSON,
          pages: capturedPages,
          template,
          metadata: paperMetadataRef.current,
          updatedAt,
        });
        const capturedContent = JSON.stringify(capturedContentPayload);
        const capturedRawMetadata = resolvePaperMetadata(paperMetadataRef.current);
        const capturedMetadata = {
          ...capturedRawMetadata,
          title: capturedRawMetadata.title || "Untitled Paper",
        };

        syncPromiseRef.current = syncPromiseRef.current
          .then(async () => {
            // If this sync was already cancelled before the promise chain
            // reached it, skip it silently.
            if (syncAbortController.signal.aborted) return;

            const currentUserId = userIdRef.current || currentUserIdSync;
            if (!currentUserId) return;

            setSaveState("saving");

            const editorJSON = capturedJSON;
            const pages = capturedPages;
            const contentPayload = capturedContentPayload;
            const content = capturedContent;
            const metadata = capturedMetadata;
            const currentPaperId = paperIdRef.current;
            // ISSUE 1: prefer real metadata; fall back to the generator-form
            // context so the resume modal isn't "Class: — | Subject: —"
            // when the user never opened the Paper Details modal.
            const generatorCtx = useEditorStore.getState().generatorContext;
            const effectiveClassName = metadata.className || generatorCtx.className || "";
            const effectiveSubject = metadata.subject || generatorCtx.subject || "";
            const liveDocument: LiveEditorDocument = {
              // Keyed by the COMPOSED id so each set tab keeps its own draft…
              id: getLiveDocumentId(currentUserId, currentPaperId),
              userId: currentUserId,
              // …but the stored id is the BASE row id, because this field is
              // what the resume flow puts back into `?paperId=`. Storing the
              // composed id there made the suffix compound on every visit.
              paperId: persistablePaperId(currentPaperId),
              title: metadata.title,
              template,
              editorJSON,
              pages,
              metadata: {
                ...contentPayload.metadata,
                className: effectiveClassName,
                subject: effectiveSubject,
                hsatSources: hsatSourcesRef.current,
                uploadedDocs: uploadedDocsRef.current,
              },
              layout: contentPayload.layout,
              sync: {
                status: "pending",
                lastSyncedAt: null,
                error: null,
              },
              updatedAt,
              sessionId: browserSessionIdRef.current,
            };

            try {
              await saveLiveDocument(liveDocument);
              setEditorContent(content);

              const isOnline =
                typeof navigator !== "undefined" ? navigator.onLine : true;
              if (!isOnline) {
                setSaveState("offline");
                return;
              }

              // Autosave ONLY updates existing backend papers (PUT).
              // Creating a new paper row is the user's explicit action via
              // "Paper Details" → Save.  Never POST from here — that caused
              // the empty-paper flood (#3 / CLUSTER 1).
              // Set tabs hand us paperId as "{baseId}_A|B|C" (editor/page.tsx).
              // The base paper row IS Set A, so autosave mirrors Set A to that
              // base id. B/C are variants stored inside the paper's `sets`
              // array and persist via the explicit multi-set Save — autosaving
              // them here (updatePaperAction wraps content into a lone Set A)
              // would 404 on the non-existent "{id}_B" row AND clobber Set A.
              // A bare id with no suffix (legacy) syncs as-is.
              const syncedPaperId = backendSyncTarget(currentPaperId);
              if (syncedPaperId) {
                await updatePaperAction(
                  syncedPaperId,
                  {
                    class: metadata.className,
                    subject: metadata.subject,
                    examName: metadata.title,
                    content,
                    questionRefs: [],
                    hsatSourceIds: hsatSourcesRef.current.map((s) => s.id),
                  },
                  syncAbortController.signal,
                );
              }
              // Record the success either way.
              //
              // This used to be inside the `if` above, so a tab with no backend
              // row (an unsaved draft, or set tab B/C) left its stored status on
              // "pending" forever — and "pending" is indistinguishable from "a
              // sync that never finished". Nothing then existed to clear an
              // older "failed", so a single historical failure was displayed on
              // every subsequent load of that draft until the teacher happened
              // to type something.
              //
              // For those tabs the local IndexedDB write IS the whole job, and
              // it just succeeded, so "synced" is the honest record.
              await saveLiveDocument({
                ...liveDocument,
                sync: {
                  status: "synced",
                  lastSyncedAt: new Date().getTime(),
                  error: null,
                },
              });
              setSaveState("saved");
            } catch (error: any) {
              // A newer sync cancelled this one — not an error, just move on.
              if (error instanceof SyncCancelledError) return;
              console.error("Live sync error:", error);
              await saveLiveDocument({
                ...liveDocument,
                sync: {
                  status: "failed",
                  lastSyncedAt: null,
                  error: error?.message || "Sync failed",
                },
              });
              setSaveState("failed");
            }
          })
          .catch((err) => console.error("Sync chain error:", err));
      }, 1000),
    [template, setEditorContent, setSaveState],
  );

  const editor = useEditor(
    {
      immediatelyRender: false,
      extensions: getTiptapExtensions(),
      content: createEmptyDocument(),
      editorProps: {
        attributes: {
          id: "tiptap-paper-container",
          class: "document-editor focus:outline-none text-black",
          "data-template": template,
          spellcheck: "true",
        },
        // Cluster C.3 — route any pasted image through the FloatImage
        // NodeView so it gets the same resize handles and alignment
        // controls as a menu-inserted image. The default paste path
        // dropped pasted images as raw inline `image` nodes which
        // (a) rendered at native size with no handles and (b) failed
        // to insert at all inside a `questionBlock` whose schema
        // doesn't list inline images. We intercept the `paste` event,
        // find the first image item, convert it to a data: URL, and
        // dispatch `insertFloatImage` — the same path the toolbar's
        // Image button uses. Non-image pastes fall through unchanged
        // so text/HTML pastes work normally.
        handlePaste: (_view, event) => {
          const items = event.clipboardData?.items;
          if (!items || items.length === 0) return false;
          for (let i = 0; i < items.length; i++) {
            const item = items[i];
            if (!item.type?.startsWith("image/")) continue;
            const file = item.getAsFile();
            if (!file) continue;
            event.preventDefault();
            const reader = new FileReader();
            reader.onload = (ev) => {
              const src = String(ev.target?.result || "");
              if (!src) return;
              const e = (window as any).__activeEditor;
              if (e && !e.isDestroyed) {
                e.chain().focus().insertFloatImage({ src }).run();
              }
            };
            reader.readAsDataURL(file);
            return true; // signal we handled the paste
          }
          return false; // text/html pastes unchanged
        },
      },
      onCreate: ({ editor }) => {
        if (typeof window !== "undefined") {
          (window as any).__activeEditor = editor;
          // PERF: expose a synchronous content-builder so the page's Save
          // handler can read the live editor at click time. This replaces
          // the per-keystroke `setEditorContent(JSON.stringify(...))` hot
          // path that re-rendered every Zustand subscriber on each
          // keystroke and re-serialized any base64 figures in the doc.
          (window as any).__activeEditorBuildContent = (
            metadata?: PaperMetadata | null,
          ) => {
            if (!editor || editor.isDestroyed) return "";
            const updatedAt = Date.now();
            const editorJSON = editor.getJSON();
            const pages = extractPagesFromDoc(editor.state.doc);
            const payload = buildPersistedPaperContent({
              editorJSON,
              pages,
              template: useEditorStore.getState().template,
              metadata: metadata ?? paperMetadataRef.current,
              updatedAt,
            });
            return JSON.stringify(payload);
          };
          (window as any).__activeEditorDestroy = () => {
            try {
              if (editor && !editor.isDestroyed) {
                if (editor.view) {
                  (editor.view as any).domObserver?.stop?.();
                }
                editor.destroy();
              }
            } catch (e) {
              console.error("Error during activeEditorDestroy:", e);
            }
          };
        }
      },
      onDestroy: () => {
        if (typeof window !== "undefined") {
          (window as any).__activeEditor = null;
          (window as any).__activeEditorBuildContent = null;
          (window as any).__activeEditorDestroy = null;
        }
      },
      onUpdate: ({ editor }) => {
        // PERF: do NOT serialize the doc here. The old path did
        // `editor.getJSON()` + `extractPagesFromDoc` + `JSON.stringify` on
        // every keystroke, which is O(doc-size) and re-rendered every
        // store subscriber (including the entire EditorPage). For a paper
        // with inlined base64 SVG figures that meant ~50-200ms of work
        // per keystroke. Persisting and serializing now happens inside
        // `debouncedLiveSync` (1s) and on the Save click via
        // `__activeEditorBuildContent`.
        if (useEditorStore.getState().saveState !== "saving") {
          setSaveState("saving");
        }
        debouncedNumbering(editor);
        debouncedPageState(editor);
        debouncedSectionSummaries(editor);
        debouncedLiveSync(editor);
      },
    },
    [],
  );

  useEffect(() => {
    if (!editor) return;
    // Preserve any non-attribute editorProps (notably handlePaste from the
    // initial useEditor config — see Cluster C.3). TipTap's setOptions
    // shallow-merges at the top level, so passing a bare
    // `editorProps: { attributes }` here loses every other editorProps key
    // from `editor.options.editorProps`. ProseMirror's `view.setProps`
    // happens to still merge into `view._props` so pastes keep working
    // today, but TipTap may re-derive view props from editor.options in
    // the future. Explicitly spreading sidesteps that fragility.
    editor.setOptions({
      editorProps: {
        ...editor.options.editorProps,
        attributes: {
          id: "tiptap-paper-container",
          class: "document-editor focus:outline-none text-black",
          "data-template": template,
          spellcheck: "true",
        },
      },
    });
  }, [editor, template]);

  // Local offline detection for the live sync indicator.

  useEffect(() => {
    const handleOnline = () => {
      const state = useEditorStore.getState().saveState;
      if (
        (state === "offline" || state === "failed") &&
        editor &&
        !editor.isDestroyed
      ) {
        setSaveState("saving");
        debouncedLiveSync(editor);
        debouncedLiveSync.flush();
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
  }, [debouncedLiveSync, editor, setSaveState]);

  useEffect(() => {
    return () => {
      debouncedNumbering.cancel();
      debouncedPageState.cancel();
      debouncedSectionSummaries.cancel();
      // ISSUE 1: flush rather than cancel — the debounce window may still
      // hold the latest edits. flush() invokes the function synchronously,
      // which writes the latest state to IndexedDB inside the sync chain.
      // Losing this would re-introduce the navigation-loss bug.
      debouncedLiveSync.flush();
    };
  }, [
    debouncedNumbering,
    debouncedPageState,
    debouncedSectionSummaries,
    debouncedLiveSync,
  ]);

  // ── ISSUE 1: flush pending sync before teardown ────────────────────
  // The 1-second debounce meant the last edits in the window vanished if
  // the user navigated away or reloaded immediately. We now flush the
  // debouncer (which writes to IndexedDB synchronously inside the chain),
  // then await the in-flight server sync before destroying the editor.
  useEffect(() => {
    const flushAndAwait = async () => {
      try {
        debouncedLiveSync.flush();
      } catch (e) {
        console.error("Failed to flush live sync on exit:", e);
      }
      // Give the sync chain a tick to enqueue, then await it. We bound the
      // wait so beforeunload doesn't deadlock the browser.
      try {
        await Promise.race([
          syncPromiseRef.current,
          new Promise((r) => setTimeout(r, 1500)),
        ]);
      } catch {
        /* swallow — IndexedDB save already happened inside flush */
      }
    };

    const handleGlobalClick = (event: MouseEvent) => {
      let target = event.target as HTMLElement | null;
      while (target && target.tagName !== "A") {
        target = target.parentElement;
      }
      if (!(target && target.tagName === "A")) return;

      const href = target.getAttribute("href");
      if (!href || !href.startsWith("/") || href.startsWith("/editor")) return;

      // Flush the debounce immediately so the latest edits hit IndexedDB
      // before the editor unmounts. The IDB save inside the sync chain is
      // best-effort but sufficient to recover state on the next mount.
      try {
        debouncedLiveSync.flush();
      } catch (e) {
        console.error("Failed to flush sync on link click:", e);
      }

      // We intentionally do NOT destroy the editor here. Letting Next's
      // router unmount it naturally means React's useEffect cleanup runs
      // and the standard destroy path fires AFTER our flush. Manually
      // destroying here (the previous behaviour) caused the last edits to
      // be dropped because the debouncer was cancelled in the cleanup
      // effect (lines below) before our flush could persist them.
    };

    const handleBeforeUnload = () => {
      try {
        debouncedLiveSync.flush();
      } catch {}
    };

    // pagehide is the modern, reliable "tab is leaving" signal in BFCache-aware
    // browsers; beforeunload is fired by some browsers only when something
    // user-visible is happening. Cover both.
    const handlePageHide = () => {
      try {
        debouncedLiveSync.flush();
      } catch {}
    };

    // Cover the in-app router push case (Next router doesn't fire link
    // clicks for programmatic nav). We watch for visibility changes too —
    // when the tab is hidden, flush whatever's pending.
    const handleVisibilityChange = () => {
      if (typeof document !== "undefined" && document.visibilityState === "hidden") {
        try {
          debouncedLiveSync.flush();
        } catch {}
      }
    };

    if (typeof window !== "undefined") {
      document.addEventListener("click", handleGlobalClick, { capture: true });
      window.addEventListener("beforeunload", handleBeforeUnload);
      window.addEventListener("pagehide", handlePageHide);
      document.addEventListener("visibilitychange", handleVisibilityChange);
    }

    return () => {
      if (typeof window !== "undefined") {
        document.removeEventListener("click", handleGlobalClick, {
          capture: true,
        });
        window.removeEventListener("beforeunload", handleBeforeUnload);
        window.removeEventListener("pagehide", handlePageHide);
        document.removeEventListener("visibilitychange", handleVisibilityChange);
      }
      // Fire-and-forget the final flush on unmount. The IDB save inside
      // the chain is what makes the next mount restore work; the server
      // PATCH following it is best-effort.
      flushAndAwait();
    };
  }, [debouncedLiveSync]);

  // Standard unmount effect ensuring observer is stopped first
  useEffect(() => {
    return () => {
      console.log(
        "[DEBUG TiptapEditor] NODEVIEW UNMOUNT (TiptapEditor unmount)",
      );
      if (editor && !editor.isDestroyed) {
        console.log(
          "[DEBUG TiptapEditor] EDITOR DESTROY START (lifecycle cleanup)",
        );
        try {
          if (editor.view) {
            (editor.view as any).domObserver?.stop?.();
          }
          editor.destroy();
          console.log(
            "[DEBUG TiptapEditor] EDITOR DESTROY COMPLETE (lifecycle cleanup)",
          );
        } catch (e) {
          console.error("Error during unmount lifecycle destroy:", e);
        }
      }
    };
  }, [editor]);

  // Handle question insertion from AI generator
  const questionsToAppend = useEditorStore((state) => state.questionsToAppend);
  const clearQuestionsToAppend = useEditorStore(
    (state) => state.clearQuestionsToAppend,
  );
  const sectionsToAppend = useEditorStore((state) => state.sectionsToAppend);
  const clearSectionsToAppend = useEditorStore(
    (state) => state.clearSectionsToAppend,
  );
  const questionRemovals = useEditorStore((state) => state.questionRemovals);
  const consumeQuestionRemovals = useEditorStore(
    (state) => state.consumeQuestionRemovals,
  );
  const instructionsToAppend = useEditorStore((state) => state.instructionsToAppend);
  const clearInstructionsToAppend = useEditorStore(
    (state) => state.clearInstructionsToAppend,
  );

  // Floating question actions (Generate image / Swap / Delete). Driven by DOM
  // delegation over the editor rather than callbacks threaded through every
  // NodeView — see lib/use-question-menu.ts.
  const questionMenu = useQuestionMenu(editor);

  const lastLoadedContentRef = useRef<string | null>(null);
  // documentLoadedRef / documentLoadedSignal: guard for deferred insertions
  // (questionsToAppend, sectionsToAppend) that must not run until the IDB
  // async load has finished setting editor content.
  const documentLoadedRef = useRef(false);
  const [documentLoadedSignal, setDocumentLoadedSignal] = useState(0);

  useEffect(() => {
    if (!editor || editor.isDestroyed) return;
    if (initialContent === undefined) return;

    const currentUserId = sessionData?.user?.id;
    if (!currentUserId) return;

    const loadKey = `${currentUserId}:${paperId ?? "current"}:${serverUpdatedAt ?? "local"}:${contentVersion}:${initialContent}`;
    if (lastLoadedContentRef.current === loadKey) return;
    lastLoadedContentRef.current = loadKey;
    // Mark document as NOT loaded while the async IDB fetch is in flight.
    documentLoadedRef.current = false;

    let cancelled = false;

    const loadLatestDocument = async () => {
      const currentPaperId = paperIdRef.current;
      const serverUpdatedTime = serverUpdatedAt
        ? new Date(serverUpdatedAt).getTime()
        : 0;

      let contentToLoad = normalizeInitialContent(initialContent ?? "");
      let liveDocument: LiveEditorDocument | null = null;

      // An approved generation replaces the tab's document outright. Skipping
      // the IndexedDB read (rather than reading it and ignoring it) also stops
      // the stale draft from being re-adopted by the `paperId` reconciliation
      // below.
      if (forceInitialContent) {
        queueMicrotask(() => {
          if (cancelled || editor.isDestroyed) return;
          editor.commands.setContent(contentToLoad, { emitUpdate: false });
          const pages = extractPagesFromDoc(editor.state.doc);
          setPages(pages);
          setEditorContent(
            JSON.stringify(
              buildPersistedPaperContent({
                editorJSON: editor.getJSON(),
                pages,
                template,
                metadata: paperMetadataRef.current,
                updatedAt: Date.now(),
              }),
            ),
          );
          updateSectionSummaries(editor);
          updateQuestionNumbers(editor);
          setSaveState(
            typeof navigator !== "undefined" && !navigator.onLine
              ? "offline"
              : "saved",
          );
          documentLoadedRef.current = true;
          setDocumentLoadedSignal((s) => s + 1);
          // Persist immediately so the approved paper survives a reload even
          // if the teacher never types.
          debouncedLiveSync(editor);
          debouncedLiveSync.flush();
        });
        return;
      }

      const { base: currentBase, set: currentSet } = splitPaperId(currentPaperId);

      try {
        if (currentPaperId) {
          liveDocument = await getLiveDocument(getLiveDocumentId(currentUserId, currentPaperId));
          // Fallback to the pre-set-tabs key (e.g. current_A -> current,
          // paper123_A -> paper123), which only Set A may adopt.
          if (!liveDocument && currentBase && (currentSet ?? "A") === "A") {
            liveDocument = await getLiveDocument(
              getLiveDocumentId(currentUserId, currentBase),
            );
          }
        }
      } catch (error) {
        console.error("Failed to load live editor state:", error);
      }

      // A draft is adoptable when it belongs to this tab's paper — either it
      // was written for this exact id, or it predates the per-set keys and
      // carries the base id (Set A only, handled by the fallback read above).
      const draftBase = basePaperId(liveDocument?.paperId);
      const draftMatchesTab =
        !currentBase ||
        currentBase === DRAFT_PAPER_ID ||
        !draftBase ||
        draftBase === currentBase;

      if (
        liveDocument &&
        draftMatchesTab &&
        (!currentPaperId || liveDocument.updatedAt >= serverUpdatedTime)
      ) {
        contentToLoad = ensurePageDocument(liveDocument.editorJSON);
        // The draft knows about a backend row this tab doesn't (the paper was
        // saved in a previous session): adopt its id and tell the page so the
        // URL and autosave target the real row.
        if (
          (!currentBase || currentBase === DRAFT_PAPER_ID) &&
          draftBase &&
          draftBase !== DRAFT_PAPER_ID
        ) {
          paperIdRef.current = withSetSuffix(draftBase, currentSet ?? "A");
          onPaperCreatedRef.current?.(draftBase);
        }
      }

      if (cancelled || editor.isDestroyed) return;

      queueMicrotask(() => {
        if (cancelled || editor.isDestroyed) return;
        editor.commands.setContent(contentToLoad, { emitUpdate: false });
        const pages = extractPagesFromDoc(editor.state.doc);
        const editorJSON = editor.getJSON();
        const updatedAt = liveDocument?.updatedAt || Date.now();
        const contentPayload = buildPersistedPaperContent({
          editorJSON,
          pages,
          template,
          metadata: paperMetadataRef.current,
          updatedAt,
        });

        setPages(pages);
        setEditorContent(JSON.stringify(contentPayload));
        updateSectionSummaries(editor);
        // A stored "failed" is history, not current state, and it is only
        // meaningful for a tab that actually has a backend row to push to.
        // Showing it on an unsaved draft (or on set tab B/C) reports the
        // failure of a request that is never attempted for those tabs — the
        // draft is safely in IndexedDB, which is all "saved" claims.
        const staleFailure =
          liveDocument?.sync.status === "failed" &&
          Boolean(backendSyncTarget(currentPaperId));
        setSaveState(
          typeof navigator !== "undefined" && !navigator.onLine
            ? "offline"
            : staleFailure
              ? "failed"
              : "saved",
        );
        // Signal dependent effects (questionsToAppend, sectionsToAppend) that
        // the document is ready.  Must come AFTER setContent so they insert
        // into the freshly-loaded document, not an empty one.
        documentLoadedRef.current = true;
        setDocumentLoadedSignal((s) => s + 1);
      });
    };

    loadLatestDocument();

    return () => {
      cancelled = true;
    };
  }, [
    editor,
    initialContent,
    contentVersion,
    forceInitialContent,
    paperId,
    serverUpdatedAt,
    sessionData?.user?.id,
    setEditorContent,
    setPages,
    setSaveState,
    template,
    debouncedLiveSync,
  ]);

  useEffect(() => {
    if (!instructionsToAppend || instructionsToAppend.length === 0 || !editor) return;

    const instructions = [...instructionsToAppend];
    clearInstructionsToAppend();

    queueMicrotask(() => {
      if (editor.isDestroyed) return;

      let hasHeader = false;
      editor.state.doc.descendants((node) => {
        if (node.type.name === "paperHeaderBlock") {
          hasHeader = true;
          return false;
        }
      });

      const insertPosition = getLastPageInsertPos(editor);
      
      const contentToInsert: any[] = [];
      
      contentToInsert.push({
        type: "instructionBlock",
        attrs: {
          variant: "generated",
          summaryItems: instructions,
        },
        content: [{ type: "paragraph" }],
      });

      editor.commands.insertContentAt(insertPosition, contentToInsert);
      
      if (!hasHeader) {
        editor.commands.insertContentAt(0, defaultHeaderJSON);
      }

      editor.commands.focus("end");
      scrollToDocumentPosition(editor, insertPosition);
      debouncedLiveSync(editor);
      debouncedLiveSync.flush();
    });
  }, [instructionsToAppend, editor, clearInstructionsToAppend, debouncedLiveSync]);

  useEffect(() => {
    // Guard: don't consume pending questions until the IDB load has placed the
    // correct base content in the editor.  Without this, questions are
    // appended to an empty document and then overwritten when the async IDB
    // load completes — the merge is lost.
    if (questionsToAppend.length === 0 || !editor || !documentLoadedRef.current) return;

    const questions = [...questionsToAppend];
    clearQuestionsToAppend();

    const contentToInsert: any[] = questions.flatMap((q) => buildQuestionBlocks(q));

    queueMicrotask(() => {
      if (editor.isDestroyed) return;

      let hasHeader = false;
      editor.state.doc.descendants((node: any) => {
        if (node.type.name === "paperHeaderBlock") {
          hasHeader = true;
          return false;
        }
      });

      const insertPosition = getLastPageInsertPos(editor);
      editor.commands.insertContentAt(insertPosition, contentToInsert);
      
      if (!hasHeader) {
        editor.commands.insertContentAt(0, defaultHeaderJSON);
      }

      editor.commands.focus("end");
      scrollToDocumentPosition(editor, insertPosition);

      // Force a live sync immediately so the AI generated questions are persisted.
      debouncedLiveSync(editor);
      debouncedLiveSync.flush();
    });
  // documentLoadedSignal is intentional: re-fire when content is loaded so
  // any pending questions (queued before doc was ready) get inserted.
  }, [questionsToAppend, editor, clearQuestionsToAppend, debouncedLiveSync, documentLoadedSignal]);

  // Handle section-wise insertion from AI generator
  useEffect(() => {
    if (sectionsToAppend.length === 0 || !editor || !documentLoadedRef.current) return;

    const sections = [...sectionsToAppend];
    clearSectionsToAppend();

    // ISSUE 2: dedupe section headers. The review tray can insert into the
    // same section in multiple passes; without this check, every pass adds
    // a fresh "Section A" header in front of its questions and breaks the
    // realized header count.
    //
    // Multi-set (Comparison Workspace): a section carries an optional
    // `setLabel`. The header is rendered as "Set B · Section A" and the dedupe
    // is scoped by that rendered text, so questions from different sets coexist
    // in ONE document without merging under a shared "Section A" header — the
    // regression that forced "clear the editor before inserting the next set".
    // Sections with no setLabel keep the bare-title behaviour exactly.
    const displayTitle = (section: (typeof sections)[number]) => {
      const bare = String(section.title || "").trim();
      const label = String(section.setLabel || "").trim();
      return label ? `Set ${label} · ${bare}` : bare;
    };

    const existingSectionTitles = new Set<string>();
    editor.state.doc.descendants((node: any) => {
      if (node.type.name === "sectionBlock") {
        const title = String(node.textContent || "").trim();
        if (title) existingSectionTitles.add(title);
      }
    });

    const contentToInsert: any[] = [];
    sections.forEach((section) => {
      const sectionTitle = displayTitle(section);
      if (sectionTitle && !existingSectionTitles.has(sectionTitle)) {
        contentToInsert.push({
          type: "sectionBlock",
          content: [{ type: "text", text: sectionTitle }],
        });
        existingSectionTitles.add(sectionTitle);
      }

      // Insert each question in this section
      section.questions.forEach((q) => {
        contentToInsert.push(...buildQuestionBlocks(q));
      });
    });

    queueMicrotask(() => {
      if (editor.isDestroyed) return;

      let hasHeader = false;
      editor.state.doc.descendants((node: any) => {
        if (node.type.name === "paperHeaderBlock") {
          hasHeader = true;
          return false;
        }
      });

      const insertPosition = getLastPageInsertPos(editor);
      editor.commands.insertContentAt(insertPosition, contentToInsert);
      
      if (!hasHeader) {
        editor.commands.insertContentAt(0, defaultHeaderJSON);
      }

      editor.commands.focus("end");
      scrollToDocumentPosition(editor, insertPosition);

      // Force a live sync immediately so the AI generated questions are persisted.
      debouncedLiveSync(editor);
      debouncedLiveSync.flush();
    });
  }, [sectionsToAppend, editor, clearSectionsToAppend, debouncedLiveSync, documentLoadedSignal]);

  // ── Tray "Undo" → remove a previously inserted question from the doc ──
  // The review tray records every generated question and lets the teacher
  // pull one back out after inserting. We match by section title + the
  // first ~120 chars of content (enough to disambiguate within a section
  // without being fragile to whitespace tweaks).
  useEffect(() => {
    if (questionRemovals.length === 0 || !editor) return;
    if (editor.isDestroyed) {
      consumeQuestionRemovals();
      return;
    }

    const normalize = (s: string) => s.replace(/\s+/g, " ").trim().slice(0, 120);
    const targets = questionRemovals.map((r) => ({
      sectionTitle: normalize(r.sectionTitle),
      content: normalize(r.content),
    }));

    let currentSectionTitle = "";
    const removalsToRun: { from: number; to: number }[] = [];

    editor.state.doc.descendants((node: any, pos: number) => {
      if (node.type.name === "sectionBlock") {
        currentSectionTitle = normalize(String(node.textContent || ""));
        return;
      }
      if (
        node.type.name !== "questionBlock" &&
        node.type.name !== "groupedQuestionBlock"
      ) {
        return;
      }
      const nodeText = normalize(String(node.textContent || ""));
      const hit = targets.find(
        (t) =>
          (t.sectionTitle === "" || t.sectionTitle === currentSectionTitle) &&
          nodeText.startsWith(t.content.slice(0, 60)),
      );
      if (hit) {
        removalsToRun.push({ from: pos, to: pos + node.nodeSize });
      }
    });

    if (removalsToRun.length > 0) {
      // Delete bottom-up so earlier positions stay valid.
      removalsToRun
        .sort((a, b) => b.from - a.from)
        .forEach(({ from, to }) => {
          editor.commands.deleteRange({ from, to });
        });
      debouncedLiveSync(editor);
      debouncedLiveSync.flush();
    }

    consumeQuestionRemovals();
  }, [questionRemovals, editor, consumeQuestionRemovals, debouncedLiveSync]);

  // Find/Replace state
  const [showFindReplace, setShowFindReplace] = useState(false);

  if (!isClient) return null;

  return (
    <div className="flex-1 flex flex-col h-full bg-transparent overflow-hidden">
      {editor && (
        <EditorToolbar
          editor={editor}
          onFindReplace={() => setShowFindReplace((v) => !v)}
          paperId={paperIdRef.current}
          exportType={exportType}
        />
      )}
      {editor && showFindReplace && (
        <FindReplace
          editor={editor}
          onClose={() => setShowFindReplace(false)}
        />
      )}
      {/* Toolbar spans the full width above; the panels flank the canvas
          below it. `min-h-0` on the row is what lets the canvas scroll
          instead of the whole column growing past the viewport. */}
      <div className="flex min-h-0 flex-1">
        {leftPanel}
        <div
          // `data-editor-scroll` is the handle the document panel's scroll spy
          // looks for — it needs THIS element, not the window, and finding it
          // by class would break the first time these utilities are edited.
          data-editor-scroll=""
          className={`editor-canvas min-w-0 flex-1 overflow-auto overscroll-contain custom-scrollbar print:bg-white print:p-0${
            isEnglishSubject(paperMetadata?.subject) ? " is-english-paper" : ""
          }`}
        >
          <EditorContent editor={editor} className="h-full pb-32" />
        </div>
        {rightPanel}
      </div>
      {editor && <StatusBar editor={editor} />}

      {/* Floating actions for whichever question the teacher is pointing at,
          plus the style picker it opens. Both are portalled to the body, so
          neither is clipped by the editor's scroll container and neither ends
          up rasterised into a PDF export. */}
      <QuestionHoverMenu
        target={
          questionMenu.active
            ? {
                element: questionMenu.active.element,
                text: questionMenu.active.text,
                canReplace: questionMenu.active.canReplace,
                onReplace: questionMenu.handleReplace,
                onDelete: questionMenu.handleDelete,
                onGenerateImage: questionMenu.openImageDialog,
                replacing: questionMenu.replacing,
                generatingImage: questionMenu.generatingImage,
              }
            : null
        }
        onMenuEnter={questionMenu.onMenuEnter}
        onMenuLeave={questionMenu.onMenuLeave}
      />
      <ImageStyleDialog
        open={questionMenu.styleDialogOpen}
        onOpenChange={questionMenu.setStyleDialogOpen}
        styles={questionMenu.styles}
        questionText={questionMenu.active?.text ?? ""}
        generating={questionMenu.generatingImage}
        onGenerate={questionMenu.handleGenerateImage}
      />
    </div>
  );
};

export const DocumentEditor = TiptapEditor;


export function getTiptapExtensions(isEditable = true) {
  const exts = [
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
          // Disable the built-in OrderedList so we can add our own version
          // without the auto-transform input rule (typing "1." at a line start
          // must NOT convert to an ordered list — it breaks English paragraph
          // questions that legitimately begin "1. Explain...").
          orderedList: false,
        }),
        // OrderedList without the "1. " → list auto-transform input rule.
        // List toolbar buttons and keyboard shortcut (Mod-Shift-7) still work.
        OrderedList.extend({ addInputRules() { return []; } }),
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
            "groupedQuestionBlock",
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
        // Issue 2 — placeholders are ProseMirror decorations, never real
        // text nodes. New blocks inserted by the toolbar are EMPTY; the
        // greyed prompt shown to the user comes from this extension and
        // disappears on first keystroke. `includeChildren: true` is what
        // lets us decorate paragraphs *inside* custom block nodes such as
        // questionBlock / groupedQuestionBlock (defaults to false). Using
        // `showOnlyCurrent: false` is what lets us light up every empty
        // option / sub-question simultaneously, not just the focused one.
        Placeholder.configure({
          includeChildren: true,
          showOnlyCurrent: false,
          placeholder: ({ editor, node, pos }) => {
            try {
              const $pos = editor.state.doc.resolve(pos);
              let isInsideList = false;
              for (let depth = $pos.depth; depth >= 0; depth--) {
                const ancestor = $pos.node(depth);
                const name = ancestor.type.name;
                if (name === "listItem") {
                  isInsideList = true;
                }
                if (name === "questionBlock") {
                  const qType = (ancestor.attrs?.questionType || "")
                    .toString()
                    .toUpperCase();
                  if (qType === "MCQ") {
                    return isInsideList
                      ? "Option…"
                      : "Enter MCQ stem here…";
                  }
                  if (qType === "ASSERTION_REASON") {
                    if (isInsideList) return "Option…";
                    // D — Differentiate Assertion (A) vs Reason (R)
                    // by the empty paragraph's index inside the
                    // questionBlock. The toolbar emits two empty
                    // paragraphs followed by the canonical option
                    // list, so paragraph #0 is the assertion body and
                    // paragraph #1 is the reason body. `$pos.index(d)`
                    // returns the index of the child at depth d+1 in
                    // its parent at depth d — i.e. where this empty
                    // paragraph sits in the questionBlock.
                    const childIndex = $pos.index(depth);
                    if (childIndex === 0) return "Assertion (A) …";
                    if (childIndex === 1) return "Reason (R) …";
                    return "Statement…";
                  }
                  return isInsideList
                    ? "Sub-item…"
                    : "Enter question here…";
                }
                if (name === "groupedQuestionBlock") {
                  return isInsideList
                    ? "Sub-question…"
                    : "Main question statement…";
                }
                if (name === "questionGroupBlock") {
                  return "Option statement…";
                }
                if (name === "sectionBlock") {
                  return "SECTION TITLE";
                }
                if (name === "instructionBlock") {
                  return "Instruction…";
                }
                if (name === "paperHeaderBlock") {
                  if (ancestor.type.name === "paperHeaderBlock") {
                    // Headings & paragraphs inside the header — give a
                    // generic prompt that doesn't tie to a specific slot.
                    return "Header line…";
                  }
                }
              }
            } catch {
              // fall through to the default
            }
            return "Start writing your exam paper…";
          },
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
        GroupedQuestionBlock,
        OrGroupInvariant,
        PaperHeaderBlockExt,
        MathBlock,
        InlineMath,
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
      ];
  if (!isEditable) {
    return exts.filter(e => e.name !== "placeholder");
  }
  return exts;
}
