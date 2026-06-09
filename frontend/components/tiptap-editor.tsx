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
import {
  getLatestLiveDocumentForUser,
  getLiveDocument,
  getLiveDocumentId,
  saveLiveDocument,
  type LiveEditorDocument,
} from "@/lib/live-document-db";
import { useSession } from "@/lib/auth-client";
import { updatePaperAction } from "@/actions/savePaper";
import { SyncCancelledError } from "@/lib/api-client";

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

function normalizeInitialContent(rawContent: string | undefined) {
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

// LaTeX delimiter contract (matches the LLM prompt directive in
// generation_router.py): inline math = \( ... \), display math = \[ ... \].
// $...$ is also accepted as a tolerant fallback because the editor's existing
// `$x$` InputRule already trained users on it; we transform it into the same
// inlineMath node so the rendered output is consistent.
//
// Display ( \[ ... \] ) becomes its own ProseMirror block (mathBlock); inline
// occurrences are spliced into the surrounding paragraph as inlineMath atoms.
// Without this, raw "\( ... \)" survived to the rendered question stem as
// literal backslashes — which was the bug teachers reported.
const DISPLAY_MATH_RE = /\\\[([\s\S]+?)\\\]/g;
const INLINE_MATH_RE = /\\\(([\s\S]+?)\\\)|\$([^\n$]+?)\$/g;

function buildInlineRun(text: string): any[] {
  const out: any[] = [];
  let cursor = 0;
  INLINE_MATH_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = INLINE_MATH_RE.exec(text))) {
    if (m.index > cursor) {
      out.push({ type: "text", text: text.slice(cursor, m.index) });
    }
    const latex = (m[1] ?? m[2] ?? "").trim();
    if (latex) {
      out.push({ type: "inlineMath", attrs: { latex } });
    }
    cursor = m.index + m[0].length;
  }
  if (cursor < text.length) {
    out.push({ type: "text", text: text.slice(cursor) });
  }
  return out.length > 0 ? out : [{ type: "text", text }];
}

function buildQuestionContentNodes(content: string) {
  const raw = String(content || "");
  if (!raw.trim()) {
    return [{ type: "paragraph" }];
  }

  // First split out display-math segments as standalone block nodes; the
  // remaining string is processed paragraph-by-paragraph with inline math.
  const blocks: any[] = [];
  let cursor = 0;
  DISPLAY_MATH_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = DISPLAY_MATH_RE.exec(raw))) {
    if (m.index > cursor) {
      const chunk = raw.slice(cursor, m.index);
      pushTextBlocks(chunk, blocks);
    }
    const latex = (m[1] ?? "").trim();
    if (latex) {
      blocks.push({ type: "mathBlock", attrs: { latex, displayMode: true } });
    }
    cursor = m.index + m[0].length;
  }
  if (cursor < raw.length) {
    pushTextBlocks(raw.slice(cursor), blocks);
  }

  return blocks.length > 0 ? blocks : [{ type: "paragraph" }];
}

function pushTextBlocks(chunk: string, blocks: any[]) {
  const lines = chunk.split(/\n{2,}|\n/).map((l) => l.trim()).filter(Boolean);
  for (const line of lines) {
    blocks.push({ type: "paragraph", content: buildInlineRun(line) });
  }
}

// Insertion guard for generated figures. We accept ONLY a `data:` URL (the
// validated inline-SVG figure pipeline emits these) or an absolute http(s)://
// URL. Relative paths are also accepted because the FloatImage NodeView
// resolves them against the Django origin at render time. Any other shape
// (blank, "null"/"undefined" literals, hallucinated URLs the backend already
// rejected) produces an empty src that renders as a broken-image icon — in
// that case we skip the floatImage entirely and let the question stem speak
// for itself, matching the backend's "text-self-contained on retry" contract.
function buildFigureNode(imageUrl: string | undefined | null) {
  const src = String(imageUrl || "").trim();
  if (!src) return null;
  const lower = src.toLowerCase();
  if (lower === "null" || lower === "undefined") return null;
  const isUsable =
    src.startsWith("data:") ||
    src.startsWith("http://") ||
    src.startsWith("https://") ||
    src.startsWith("/");
  if (!isUsable) return null;
  return {
    type: "floatImage",
    attrs: {
      src,
      // Alt is intentionally empty: the previous "Question visual"
      // literal was the broken-image-icon caption users saw when an
      // intermittently-failing src didn't load. The figure is decorative
      // alongside a text-self-contained stem, so no alt is the safe
      // default. (Screen readers read the stem itself.)
      alt: "",
      width: 320,
      align: "center",
    },
  };
}

// ==================================
// Main Editor Component
// ==================================
type TiptapEditorProps = {
  initialContent?: string;
  paperId?: string | null;
  serverUpdatedAt?: string | null;
  paperMetadata?: PaperMetadata;
  onPaperCreatedAction?: (paperId: string) => void;
};

export const TiptapEditor = ({
  initialContent,
  paperId = null,
  serverUpdatedAt = null,
  paperMetadata,
  onPaperCreatedAction,
}: TiptapEditorProps) => {
  const [isClient, setIsClient] = useState(false);
  const template = useEditorStore((state) => state.template);
  const { data: sessionData } = useSession();
  const userIdRef = useRef<string | null>(null);
  const paperIdRef = useRef<string | null>(paperId);
  const paperMetadataRef = useRef<PaperMetadata | undefined>(paperMetadata);
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
              id: getLiveDocumentId(currentUserId, currentPaperId),
              userId: currentUserId,
              paperId: currentPaperId,
              title: metadata.title,
              template,
              editorJSON,
              pages,
              metadata: {
                ...contentPayload.metadata,
                className: effectiveClassName,
                subject: effectiveSubject,
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
              const syncedPaperId =
                currentPaperId && currentPaperId !== "current"
                  ? currentPaperId
                  : null;
              if (syncedPaperId) {
                await updatePaperAction(
                  syncedPaperId,
                  {
                    class: metadata.className,
                    subject: metadata.subject,
                    examName: metadata.title,
                    content,
                    questionRefs: [],
                  },
                  syncAbortController.signal,
                );
                await saveLiveDocument({
                  ...liveDocument,
                  sync: {
                    status: "synced",
                    lastSyncedAt: new Date().getTime(),
                    error: null,
                  },
                });
              }
              // For unsaved drafts (syncedPaperId = null): IDB save already
              // happened above.  Show "Saved" to indicate the draft is safe
              // locally even though no backend row exists yet.
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
      ],
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

    const loadKey = `${currentUserId}:${paperId ?? "current"}:${serverUpdatedAt ?? "local"}:${initialContent}`;
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

      try {
        liveDocument = currentPaperId
          ? await getLiveDocument(
              getLiveDocumentId(currentUserId, currentPaperId),
            )
          : null;
      } catch (error) {
        console.error("Failed to load live editor state:", error);
      }

      if (
        liveDocument &&
        (currentPaperId === "current" ||
          !currentPaperId ||
          liveDocument.paperId === currentPaperId) &&
        (!currentPaperId || liveDocument.updatedAt >= serverUpdatedTime)
      ) {
        contentToLoad = ensurePageDocument(liveDocument.editorJSON);
        if (currentPaperId === "current" && liveDocument.paperId) {
          paperIdRef.current = liveDocument.paperId;
          onPaperCreatedRef.current?.(liveDocument.paperId);
        } else if (!currentPaperId && liveDocument.paperId) {
          paperIdRef.current = liveDocument.paperId;
          onPaperCreatedRef.current?.(liveDocument.paperId);
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
        setSaveState(
          typeof navigator !== "undefined" && !navigator.onLine
            ? "offline"
            : liveDocument?.sync.status === "failed"
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
    paperId,
    serverUpdatedAt,
    sessionData?.user?.id,
    setEditorContent,
    setPages,
    setSaveState,
    template,
  ]);

  useEffect(() => {
    if (!instructionsToAppend || instructionsToAppend.length === 0 || !editor) return;

    const instructions = [...instructionsToAppend];
    clearInstructionsToAppend();

    const contentToInsert = [
      {
        type: "instructionBlock",
        attrs: {
          variant: "generated",
          summaryItems: instructions,
        },
        content: [{ type: "paragraph" }],
      },
    ];

    queueMicrotask(() => {
      if (editor.isDestroyed) return;

      const insertPosition = getLastPageInsertPos(editor);
      editor.commands.insertContentAt(insertPosition, contentToInsert);
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

    const contentToInsert: any[] = [];
    questions.forEach((q) => {
      const questionContent: any[] = buildQuestionContentNodes(q.content);

      const figureNode = buildFigureNode(q.image_url);
      if (figureNode) {
        questionContent.push(figureNode);
      }

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
    const existingSectionTitles = new Set<string>();
    editor.state.doc.descendants((node: any) => {
      if (node.type.name === "sectionBlock") {
        const title = String(node.textContent || "").trim();
        if (title) existingSectionTitles.add(title);
      }
    });

    const contentToInsert: any[] = [];
    sections.forEach((section) => {
      const sectionTitle = String(section.title || "").trim();
      if (sectionTitle && !existingSectionTitles.has(sectionTitle)) {
        contentToInsert.push({
          type: "sectionBlock",
          content: [{ type: "text", text: sectionTitle }],
        });
        existingSectionTitles.add(sectionTitle);
      }

      // Insert each question in this section
      section.questions.forEach((q) => {
        const questionContent: any[] = buildQuestionContentNodes(q.content);

        const figureNode = buildFigureNode(q.image_url);
        if (figureNode) {
          questionContent.push(figureNode);
        }

        if (q.type !== "TF" && q.options && q.options.length > 0) {
          questionContent.push({
            type: "orderedList",
            content: q.options.map((opt: string) => ({
              type: "listItem",
              content: [
                {
                  type: "paragraph",
                  // Bug 1 fix: MCQ options used to wrap raw text in a single
                  // { type: "text", text: opt } node. Any LaTeX delimiters
                  // (\(\tfrac{11}{36}\), \(\dfrac{7}{25}\), \(x^2 - 5x +
                  // 6 = 0\)) survived to the rendered DOM as literal
                  // backslashes, which then made it into the PDF rasterizer
                  // unchanged. Reuse buildInlineRun so math in options gets
                  // the same inlineMath KaTeX node treatment that question
                  // stems already enjoy.
                  content: buildInlineRun(opt),
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
        />
      )}
      {editor && showFindReplace && (
        <FindReplace
          editor={editor}
          onClose={() => setShowFindReplace(false)}
        />
      )}
      <div className="flex-1 overflow-y-auto custom-scrollbar bg-transparent print:p-0">
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
          background: transparent;
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
          box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
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
          border: none;
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
        }

        .paper-header-logo-area.is-empty {
          border: 1px dashed #bbb;
          color: #888;
        }

        @media print {
          .paper-header-logo-area.is-empty {
            border: none;
          }
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

        /* Cluster C.2 — paper header Date field */
        .paper-header-date-row {
          display: flex;
          align-items: center;
          gap: 6px;
          margin-top: 6px;
          font-size: 11pt;
          color: #000000;
        }
        .paper-header-date-label {
          font-weight: 600;
        }
        /* G — single date representation. A formatted span is shown
           on top of an invisible native date input; the input still
           opens the picker on click but does not render its own
           date string, so the teacher never sees two dates. */
        .paper-header-date-picker-wrap {
          position: relative;
          display: inline-flex;
          align-items: baseline;
          cursor: pointer;
        }
        .paper-header-date-input {
          position: absolute;
          inset: 0;
          width: 100%;
          height: 100%;
          padding: 0;
          margin: 0;
          border: 0;
          opacity: 0;
          color: transparent;
          background: transparent;
          cursor: pointer;
        }
        .paper-header-date-input::-webkit-calendar-picker-indicator {
          opacity: 0;
          cursor: pointer;
        }
        .paper-header-date-display {
          font-weight: 500;
          font-size: 11pt;
          color: #000000;
          padding: 1px 4px;
          border-bottom: 1px dashed #c4c4c8;
        }
        .paper-header-actions {
          display: flex;
          flex-direction: column;
          gap: 4px;
          align-items: flex-end;
        }
        .paper-header-action {
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
          cursor: pointer;
        }
        .paper-header-action.is-active {
          background: #18181b;
          color: #ffffff;
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
          margin: 10px 0 2px;
          break-inside: avoid;
          page-break-inside: avoid;
        }

        .section-header {
          display: block;
          text-align: center;
          padding: 2px 0;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          font-size: 10pt;
        }

        .section-title {
          display: inline;
        }

        .section-summary {
          display: inline;
          margin-left: 8px;
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

        /* ===== Drag Handles ===== */
        /*
         * .block-drag-handle sits in the left margin of the page (inside the
         * 56 px left padding of .doc-page-content so it is never clipped by
         * overflow:hidden).  It is absolutely positioned relative to the
         * block's own NodeViewWrapper which already has position:relative.
         */
        .block-drag-handle {
          position: absolute;
          left: -22px;
          top: 50%;
          transform: translateY(-50%);
          width: 18px;
          height: 26px;
          display: flex;
          align-items: center;
          justify-content: center;
          opacity: 0;
          transition: opacity 0.15s ease;
          cursor: grab;
          color: #999;
          border-radius: 3px;
          user-select: none;
          z-index: 10;
        }

        /* Reveal on hover of the parent block */
        .question-block:hover > .block-drag-handle,
        .section-block:hover > .block-drag-handle,
        .instruction-block:hover > .block-drag-handle,
        .question-group:hover > .block-drag-handle {
          opacity: 1;
        }

        .block-drag-handle:hover {
          color: #333;
          background: rgba(0, 0, 0, 0.07);
        }

        .block-drag-handle:active {
          cursor: grabbing;
          color: #000;
          background: rgba(0, 0, 0, 0.12);
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
          grid-template-columns: 56px 1fr 72px;
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
          display: flex;
          align-items: center;
          justify-content: center;
          white-space: nowrap;
        }

        .question-marks-input {
          width: 44px;
          min-width: 44px;
          border: none;
          text-align: center;
          font-family: inherit;
          font-size: 11pt;
          background: transparent;
          padding: 0 2px;
          margin: 0;
          outline: none;
          color: #000000;
          -moz-appearance: textfield;
          appearance: textfield;
        }

        .question-marks-input::-webkit-inner-spin-button,
        .question-marks-input::-webkit-outer-spin-button {
          -webkit-appearance: none;
          margin: 0;
        }

        .question-marks-label {
          font-size: 10pt;
          margin-left: 2px;
        }

        .question-controls {
          /* Cluster B.3 — push the hover-popup column further to the right
             of the question block and give it a bigger inter-button gap so
             the add-subquestion "+" no longer visually collides with the
             marks-edit input that sits flush with the block's right edge.
             The earlier -28px placement put the "+" within ~4px of the M
             label in grouped-OR / grouped-questions layouts. */
          position: absolute;
          right: -44px;
          top: 4px;
          opacity: 0;
          transition: opacity 0.2s ease;
          display: flex;
          flex-direction: column;
          gap: 6px;
          padding-left: 4px;
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

        .question-add-sub {
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

        /* ===== Grouped Question (a, b, ...) ===== */
        .grouped-question-block .question-body ul,
        .grouped-question-block .question-body ol {
          margin: 6px 0 0;
          padding: 0;
          list-style: none;
          display: block;
          grid-template-columns: none;
          column-gap: 0;
          row-gap: 0;
        }

        .grouped-question-block .question-body ol {
          counter-reset: subq;
        }

        .grouped-question-block .question-body ol li,
        .grouped-question-block .question-body ul li {
          display: flex;
          align-items: flex-start;
          gap: 4px;
          margin: 2px 0;
        }

        /* default (alpha): (a) (b) (c) */
        .grouped-question-block .question-body ol li::before,
        .grouped-question-block[data-label-style="alpha"] .question-body ol li::before {
          counter-increment: subq;
          content: "(" counter(subq, lower-alpha) ") ";
          font-weight: 700;
          min-width: 22px;
          display: inline-flex;
          justify-content: flex-start;
        }

        /* numeric: 1. 2. 3. */
        .grouped-question-block[data-label-style="numeric"] .question-body ol li::before {
          counter-increment: subq;
          content: counter(subq, decimal) ". ";
          font-weight: 700;
          min-width: 22px;
          display: inline-flex;
          justify-content: flex-start;
        }

        /* roman: (i) (ii) (iii) */
        .grouped-question-block[data-label-style="roman"] .question-body ol li::before {
          counter-increment: subq;
          content: "(" counter(subq, lower-roman) ") ";
          font-weight: 700;
          min-width: 28px;
          display: inline-flex;
          justify-content: flex-start;
        }

        .grouped-question-block .question-body ul li::before {
          content: "- ";
          font-weight: 700;
          min-width: 18px;
          display: inline-flex;
          justify-content: flex-start;
        }

        .grouped-question-block .question-body ol li > p,
        .grouped-question-block .question-body ul li > p {
          margin: 0;
        }

        /* Label style picker */
        .question-label-style-picker {
          display: flex;
          align-items: center;
        }

        .question-label-style-select {
          border: 1px solid #000000;
          background: #ffffff;
          color: #000000;
          border-radius: 4px;
          padding: 1px 2px;
          font-size: 9pt;
          height: 20px;
          cursor: pointer;
          outline: none;
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
        /*
         * Group wrapper for OR / choice questions. No borders added here;
         * each individual question inside has its own .question-row border.
         */
        .question-group {
          position: relative;
          margin: 4px 0;
          padding: 0;
          background: #ffffff;
          break-inside: avoid;
          page-break-inside: avoid;
        }

        .question-group-header {
          display: flex;
          align-items: baseline;
          gap: 8px;
          padding: 1px 0;
        }

        .question-group-number {
          font-weight: 700;
          font-size: 11pt;
          flex-shrink: 0;
        }

        .question-group-label-text {
          font-weight: 700;
          font-size: 10pt;
          letter-spacing: 0.04em;
          text-transform: uppercase;
          flex: 1;
        }

        .question-group-label {
          text-align: center;
          font-weight: 700;
          font-size: 10pt;
          letter-spacing: 0.08em;
          text-transform: uppercase;
        }

        .question-group-content {
          margin-top: 2px;
        }

        /* Issue 4 — the OR separator between branches of an "answer any one"
           group is rendered as a CSS pseudo-element, NOT as a paragraph
           sibling. This is the single source of truth for the OR label: it
           cannot be deleted by drag-reorder, copied past, or split, because
           it is not part of the document tree at all. The OrGroupInvariant
           extension strips legacy "OR" paragraph children on first load so
           older papers do not show the label twice. The combinator pairs
           cover all four orderings of questionBlock / groupedQuestionBlock
           siblings; the inner-doc selectors apply in the editor while the
           data-attribute selectors apply to the serialised renderHTML
           output used by exports and previews. */
        .question-group-content > [data-type="question-block"] + [data-type="question-block"]::before,
        .question-group-content > [data-type="grouped-question-block"] + [data-type="grouped-question-block"]::before,
        .question-group-content > [data-type="question-block"] + [data-type="grouped-question-block"]::before,
        .question-group-content > [data-type="grouped-question-block"] + [data-type="question-block"]::before,
        [data-type="question-group"] > [data-type="question-block"] + [data-type="question-block"]::before,
        [data-type="question-group"] > [data-type="grouped-question-block"] + [data-type="grouped-question-block"]::before,
        [data-type="question-group"] > [data-type="question-block"] + [data-type="grouped-question-block"]::before,
        [data-type="question-group"] > [data-type="grouped-question-block"] + [data-type="question-block"]::before {
          content: "OR";
          display: block;
          text-align: center;
          font-weight: 700;
          font-size: 11pt;
          color: #000;
          margin: 8px 0;
          letter-spacing: 0.05em;
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

        /* ===== Placeholder =====
           Issue 2 — empty-node placeholders live in ProseMirror decorations
           applied by @tiptap/extension-placeholder. The decoration sets
           .is-empty and a data-placeholder attribute on every empty
           text block. The rule below renders that attribute as a ghost
           line via ::before; the host paragraph stays empty so saves /
           exports contain no placeholder bleed-through.

           The legacy :first-child filter only covered the top-level
           empty document; insertion through custom block nodes
           (questionBlock, groupedQuestionBlock, instructionBlock, …) now
           triggers the same affordance because we removed that selector
           and added [data-placeholder]. */
        .ProseMirror .is-empty[data-placeholder]::before {
          content: attr(data-placeholder);
          float: left;
          color: #71717a;
          pointer-events: none;
          height: 0;
          font-style: italic;
        }
        .ProseMirror .is-editor-empty:first-child::before {
          content: attr(data-placeholder);
          float: left;
          color: #71717a;
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
            background: #ffffff !important;
            color: #000000 !important;
          }

          .document-editor *, .ProseMirror * {
            color: #000000 !important;
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
            background: #ffffff !important;
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
          .block-drag-handle,
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
