"use client";

/**
 * The dashboard is a working surface, not a board of statistics.
 *
 * Two things happen here and they are deliberately the same thing. A teacher
 * can ask the assistant anything — it is a general assistant and answers as
 * one. When what they want is a paper, the conversation becomes a *session*:
 * it grows a spec, asks its outstanding question as something you tap rather
 * than type, and ends by running the real generation with the press check
 * over it. A session can be parked and picked up later, because a teacher
 * setting up a paper gets interrupted.
 *
 * The generation itself is untouched — this calls the same
 * `/api/generation/questions/stream` the generator form does, and hands the
 * result to the editor through the same store.
 */

import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  ArrowRight,
  MessageSquarePlus,
  PanelLeft,
  Pause,
  Play,
  Trash2,
} from "lucide-react";

import {
  PromptInputBox,
  PromptTooltipProvider,
  type PromptAttachment,
} from "@/components/ui/ai-prompt-box";
import { FollowUpCard } from "@/components/dashboard/follow-up-card";
import {
  PressCheck,
  type PressRow,
  type PressStageId,
} from "@/components/dashboard/press-check";
import { ChatBackdrop } from "@/components/dashboard/chat-backdrop";
import { PaperDesignPanel } from "@/components/paper-design-panel";
import { usePaperDesign } from "@/lib/use-paper-design";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { generationRunner } from "@/lib/generation-runner";
import { useEditorStore } from "@/store/editor-store";
import {
  createConversation,
  deleteConversation,
  fetchConversation,
  fetchConversations,
  setConversationStatus,
  streamChatMessage,
  uploadPdfSource,
  waitForPdfSource,
  type ChatMessage,
  type Conversation,
  type ConversationStatus,
  type FollowUpPrompt,
  type PaperSpec,
} from "@/lib/api-client";
import { asStatusText, planSummaryLine } from "@/lib/plan-summary";

const SUGGESTIONS = [
  "Make a class 10 Science unit test on Light.",
  "What does the class 10 English paper look like?",
  "Draft a note to parents about the term test.",
  "Explain the CBSE competency-based question format.",
];

// The pipeline's own stage names, mapped onto the press. `pool_progress` is a
// tick inside `generating_pool`, not a stage of its own.
const STAGE_MAP: Record<string, PressStageId> = {
  reading_chapters: "reading_chapters",
  generating_assets: "generating_pool",
  generating_pool: "generating_pool",
  pool_progress: "generating_pool",
  assets_ready: "generating_pool",
  assembling: "assembling",
};

interface GenerationState {
  running: boolean;
  stage: PressStageId;
  status: string;
  rows: PressRow[];
  plannedSlots?: number;
  poolCount?: number;
  sets: string[];
  done: boolean;
}

const IDLE: GenerationState = {
  running: false,
  stage: "reading_chapters",
  status: "",
  rows: [],
  sets: [],
  done: false,
};

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={cn("flex w-full", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
          isUser ? "bg-primary text-primary-foreground" : "bg-muted text-foreground",
        )}
      >
        {/* Plain text, deliberately: the assistant answers in prose, and
            rendering model output as HTML would be an injection surface for
            no gain. `whitespace-pre-wrap` keeps its line breaks. */}
        <p className="whitespace-pre-wrap break-words">{message.content}</p>
        {(message.attachments?.length ?? 0) > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {message.attachments!.map((attachment) => (
              <span
                key={attachment.id}
                className={cn(
                  "rounded-lg px-2 py-0.5 text-xs",
                  isUser ? "bg-primary-foreground/15" : "bg-foreground/10",
                )}
              >
                {attachment.name}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function TypingDots() {
  return (
    <div className="flex items-center gap-1 rounded-2xl bg-muted px-4 py-3">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/60"
          style={{ animationDelay: `${i * 0.15}s` }}
        />
      ))}
    </div>
  );
}

const SPEC_ROW: Array<[keyof PaperSpec, string]> = [
  ["subject", "Subject"],
  ["academicClass", "Class"],
  ["board", "Board"],
  ["marks", "Marks"],
  ["difficulty", "Difficulty"],
  ["numberOfSets", "Sets"],
];

/** The session's state of play, always visible while one is open. */
function SessionHeader({
  spec,
  sourceCount,
  status,
  onPause,
  onResume,
}: {
  spec: PaperSpec;
  sourceCount: number;
  status: ConversationStatus;
  onPause: () => void;
  onResume: () => void;
}) {
  const paused = status === "paused";
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-border px-4 py-2.5">
      <span className="flex items-center gap-1.5 text-xs font-medium">
        Paper session
      </span>

      <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-3 gap-y-1">
        {SPEC_ROW.map(([key, label]) => {
          const value = spec[key];
          if (!value || Array.isArray(value)) return null;
          return (
            <span key={key} className="text-xs text-muted-foreground">
              {label} <span className="text-foreground">{value}</span>
            </span>
          );
        })}
        {sourceCount > 0 && (
          <span className="text-xs text-muted-foreground">
            Sources <span className="text-foreground">{sourceCount}</span>
          </span>
        )}
      </div>

      <Button
        variant="ghost"
        size="sm"
        onClick={paused ? onResume : onPause}
        className="shrink-0"
      >
        {paused ? (
          <>
            <Play className="mr-1.5 h-3.5 w-3.5" />
            Resume
          </>
        ) : (
          <>
            <Pause className="mr-1.5 h-3.5 w-3.5" />
            Pause
          </>
        )}
      </Button>
    </div>
  );
}

export default function DashboardPage() {
  const router = useRouter();
  const adoptGeneratedSets = useEditorStore((s) => s.adoptGeneratedSets);
  const setPaperSpecHandoff = useEditorStore((s) => s.setPaperSpecHandoff);

  const [conversations, setConversations] = React.useState<Conversation[]>([]);
  const [activeId, setActiveId] = React.useState<string | null>(null);
  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [spec, setSpec] = React.useState<PaperSpec>({});
  const [mode, setMode] = React.useState<"chat" | "paper">("chat");
  const [status, setStatus] = React.useState<ConversationStatus>("active");
  const [prompt, setPrompt] = React.useState<FollowUpPrompt | null>(null);
  const [sourceIds, setSourceIds] = React.useState<string[]>([]);
  const [canGenerate, setCanGenerate] = React.useState(false);
  const [streamingText, setStreamingText] = React.useState("");
  const [isStreaming, setIsStreaming] = React.useState(false);
  const [sidebarOpen, setSidebarOpen] = React.useState(false);
  const [generation, setGeneration] = React.useState<GenerationState>(IDLE);

  const scrollRef = React.useRef<HTMLDivElement>(null);
  const attachRef = React.useRef<(() => void) | null>(null);
  const abortedRef = React.useRef(false);

  React.useEffect(() => {
    fetchConversations()
      .then(setConversations)
      .catch(() => {
        /* An empty history is a valid first run, not an error to report. */
      });
  }, []);

  React.useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, streamingText, prompt]);

  const startNewSession = React.useCallback(() => {
    setActiveId(null);
    setMessages([]);
    setSpec({});
    setMode("chat");
    setStatus("active");
    setPrompt(null);
    setSourceIds([]);
    setCanGenerate(false);
    setStreamingText("");
    setGeneration(IDLE);
    setSidebarOpen(false);
  }, []);

  const loadConversation = React.useCallback(async (id: string) => {
    try {
      const detail = await fetchConversation(id);
      setActiveId(detail.id);
      setMessages(detail.messages || []);
      setSpec(detail.spec || {});
      setMode(detail.mode);
      setStatus(detail.status);
      setPrompt(detail.next_prompt);
      setSourceIds(detail.source_ids || []);
      setCanGenerate(Boolean(detail.can_generate));
      setGeneration(IDLE);
      setSidebarOpen(false);
    } catch {
      toast.error("Could not open that session.");
    }
  }, []);

  const changeStatus = React.useCallback(
    async (next: ConversationStatus) => {
      if (!activeId) return;
      setStatus(next);
      try {
        await setConversationStatus(activeId, next);
        setConversations((current) =>
          current.map((c) => (c.id === activeId ? { ...c, status: next } : c)),
        );
      } catch {
        toast.error("Could not update the session.");
      }
    },
    [activeId],
  );

  const handleDelete = React.useCallback(
    async (id: string) => {
      try {
        await deleteConversation(id);
        setConversations((current) => current.filter((c) => c.id !== id));
        if (activeId === id) startNewSession();
      } catch {
        toast.error("Could not delete that session.");
      }
    },
    [activeId, startNewSession],
  );

  const handleAttach = React.useCallback(
    async (file: File): Promise<PromptAttachment | null> => {
      // Not `file.type !== "application/pdf"`: browsers report an empty type
      // for files dragged from some archives and file managers, and Windows
      // occasionally reports "application/octet-stream" for a perfectly good
      // PDF. The extension is the more reliable signal, and the backend
      // validates the actual bytes regardless.
      const looksLikePdf =
        file.type === "application/pdf" ||
        file.name.toLowerCase().endsWith(".pdf");
      if (!looksLikePdf) {
        toast.error(`${file.name} isn't a PDF.`);
        return null;
      }

      const notice = toast.loading(`Reading ${file.name}…`);
      try {
        const { pdfSourceId, status, warnings } = await uploadPdfSource(file);
        warnings?.forEach((w) => toast.warning(w, { duration: 8000 }));

        // Ingestion runs on a worker thread, so the upload returning is not
        // the same as the source being usable. Generation rejects one that
        // is still processing, which would surface as a baffling failure
        // several minutes later instead of here.
        if (status !== "ready") {
          await waitForPdfSource(pdfSourceId);
        }

        toast.success(`${file.name} is ready.`, { id: notice });
        return { id: pdfSourceId, name: file.name, size: file.size };
      } catch (error: any) {
        // The real reason, not a shrug. An upload can fail for a dozen
        // reasons the teacher can act on — the file is encrypted, it is over
        // the size limit, the session expired — and "Could not upload that
        // PDF" hides every one of them.
        toast.error(error?.message || `Could not upload ${file.name}.`, {
          id: notice,
          duration: 8000,
        });
        return null;
      }
    },
    [],
  );

  const handleSend = React.useCallback(
    async (content: string, attachments: PromptAttachment[]) => {
      abortedRef.current = false;

      let conversationId = activeId;
      if (!conversationId) {
        try {
          const created = await createConversation();
          conversationId = created.id;
          setActiveId(created.id);
          setConversations((current) => [created, ...current]);
        } catch {
          toast.error("Could not start a session.");
          return;
        }
      }

      // The teacher's turn appears the instant they send it. The id is local
      // and is replaced when the conversation is next loaded.
      setMessages((current) => [
        ...current,
        { id: `local-${Date.now()}`, role: "user", content, attachments },
      ]);
      // Retire the answered question immediately; the next one arrives with
      // the reply. Leaving it up would let the teacher answer twice.
      setPrompt(null);
      setIsStreaming(true);
      setStreamingText("");

      let assembled = "";
      try {
        await streamChatMessage(
          conversationId,
          content,
          attachments,
          (event, data) => {
            if (abortedRef.current) return;
            if (event === "delta") {
              assembled += data.text ?? "";
              setStreamingText(assembled);
            } else if (event === "spec") {
              setSpec(data.spec || {});
              setMode(data.mode || "chat");
              setPrompt(data.nextPrompt ?? null);
              setSourceIds(data.sourceIds || []);
              setCanGenerate(Boolean(data.canGenerate));
              if (data.mode === "paper") setStatus("active");
            } else if (event === "done") {
              setMessages((current) => [
                ...current,
                {
                  id: data.messageId,
                  role: "assistant",
                  content: data.content ?? assembled,
                },
              ]);
              setStreamingText("");
            } else if (event === "error") {
              toast.error(data.error || "The assistant hit an error.");
            }
          },
        );
      } catch (error: any) {
        if (!abortedRef.current) {
          toast.error(error?.message || "The assistant is unreachable.");
          if (assembled) {
            setMessages((current) => [
              ...current,
              { id: `partial-${Date.now()}`, role: "assistant", content: assembled },
            ]);
          }
          setStreamingText("");
        }
      } finally {
        setIsStreaming(false);
        fetchConversations().then(setConversations).catch(() => {});
      }
    },
    [activeId],
  );

  // ── General Instructions Mode ─────────────────────────────────────────
  // The assistant records a structure the teacher described in their own words
  // ("5 MCQs and 3 short answers", "same as our weekly test") into
  // `spec.instructions`. Its presence is what turns this from a board-pattern
  // paper into one laid out purely from what they asked for.
  const customInstructions = String(spec.instructions || "").trim();
  const [gapOverrides, setGapOverrides] = React.useState<Record<string, string>>(
    {},
  );

  // Answers given in the panel win over the spec — they are the teacher's
  // latest word, and the assistant has no way to hear a button press.
  const designSettings = React.useMemo(
    () => ({
      board: String(spec.board || ""),
      academicClass: String(spec.academicClass || ""),
      subject: String(spec.subject || ""),
      difficulty: String(spec.difficulty || ""),
      marks: String(spec.marks || ""),
      numberOfSets: String(spec.numberOfSets || ""),
      ...gapOverrides,
    }),
    [spec, gapOverrides],
  );

  const paperDesign = usePaperDesign({
    instructions: customInstructions,
    settings: designSettings,
    pdfSourceIds: sourceIds,
    enabled: Boolean(customInstructions),
  });

  // Everything the generation call should use: what was agreed in chat, plus
  // the panel's answers, plus the assumed defaults the backend filled in.
  const resolvedSpec = React.useMemo(
    () => ({ ...designSettings, ...paperDesign.resolvedSettings, ...gapOverrides }),
    [designSettings, paperDesign.resolvedSettings, gapOverrides],
  );

  const resolveDesignGap = React.useCallback((field: string, value: string) => {
    if (field === "sources") return;
    setGapOverrides((prev) => ({ ...prev, [field]: value }));
  }, []);

  // A described structure has its own readiness: the panel's required gaps,
  // not the assistant's four-field check.
  const readyToGenerate = customInstructions
    ? paperDesign.ready && sourceIds.length > 0
    : canGenerate;

  // ── Generation ────────────────────────────────────────────────────────

  const handleGenerate = React.useCallback(async () => {
    if (!readyToGenerate || generation.running) return;

    setGeneration({ ...IDLE, running: true, status: "Starting the press…" });
    if (activeId) void setConversationStatus(activeId, "generating");

    const variantSets: { label: string; result: any }[] = [];
    let setA: any = null;

    try {
      // Routed through the runner rather than calling `streamSse` directly, so
      // this run registers in the same place the editor's does. Without it the
      // sitewide tracker would be blind to a paper started here — which is the
      // one case where the teacher is guaranteed to navigate away, since the
      // dashboard hands off to the editor when it finishes.
      //
      // The press-check UI below is unchanged: the runner broadcasts raw
      // events, and this callback still interprets them its own way.
      const outcome = await generationRunner.start({
        paperId: null,
        origin: "dashboard",
        multiSet: Number(resolvedSpec.numberOfSets || "1") > 1,
        payload: {
          pdfSourceIds: sourceIds,
          hsatSourceIds: [],
          // -1 is the CBSE board pattern: the blueprint decides the count.
          count: spec.numberOfQuestions ? Number(spec.numberOfQuestions) : -1,
          countType: spec.numberOfQuestions ? "custom" : "cbse",
          countVariation: spec.numberOfQuestions ? "custom" : "cbse",
          difficulty: resolvedSpec.difficulty || "medium",
          // In General Instructions Mode the teacher's own description IS the
          // blueprint, so it is sent whole. Otherwise the only instruction is
          // which chapters to draw from.
          instructions: customInstructions
            ? customInstructions
            : (spec.chapters || []).length
              ? `Chapters: ${(spec.chapters || []).join(", ")}`
              : "",
          board: spec.board || "CBSE",
          subject: resolvedSpec.subject || "",
          class: resolvedSpec.academicClass || "",
          marks: resolvedSpec.marks || "",
          qp_type: customInstructions ? "general_instructions" : "board",
          // The structure shown in the confirm card. Sending it means the
          // paper the teacher approved is the paper that gets generated.
          ...(customInstructions && paperDesign.design?.sections.length
            ? { design: paperDesign.design }
            : {}),
          mathLevel: "standard",
          include_vi_alternatives: false,
          contentScopePolicy: "strict",
          sets: Number(resolvedSpec.numberOfSets || "1"),
        },
        onEvent: (event, data) => {
          if (event === "status") {
            const stage = STAGE_MAP[data.stage];
            setGeneration((g) => ({
              ...g,
              stage: stage ?? g.stage,
              status: asStatusText(data.message) || g.status,
            }));
          } else if (event === "plan") {
            setGeneration((g) => ({
              ...g,
              stage: "plan",
              plannedSlots: Number(data.total) || g.plannedSlots,
              status: planSummaryLine(data.summary) || "Blueprint compiled",
            }));
          } else if (event === "pool") {
            setGeneration((g) => ({ ...g, poolCount: Number(data.total) || g.poolCount }));
          } else if (event === "question") {
            setGeneration((g) => ({
              ...g,
              stage: "printing",
              rows: [
                ...g.rows,
                {
                  section:
                    g.rows[g.rows.length - 1]?.section === data.section
                      ? undefined
                      : data.section,
                  number: g.rows.length + 1,
                  marks: Number(data.question?.marks ?? 1),
                  text: String(data.question?.content ?? ""),
                },
              ],
            }));
          } else if (event === "set") {
            variantSets.push({ label: data.label, result: data.result });
            setGeneration((g) => ({
              ...g,
              stage: "sets",
              sets: [...g.sets, data.label],
            }));
          } else if (event === "done") {
            setA = data.result ?? setA;
          } else if (event === "update" || event === "message") {
            setA = data;
          }
        },
      });

      // Failure is reported through the result rather than by throwing from
      // the handler: the runner contains subscriber exceptions so one bad
      // listener cannot kill a stream every other listener is reading.
      if (outcome.cancelled) {
        setGeneration(IDLE);
        if (activeId) void setConversationStatus(activeId, "active");
        return;
      }
      if (!outcome.ok) {
        throw new Error(outcome.error || "Generation failed");
      }

      setGeneration((g) => ({ ...g, done: true, status: "Paper ready" }));

      // Hand the result to the editor as an APPROVED generation: each set
      // becomes the content of its own tab the moment the editor mounts.
      //
      // Merely staging them (`setComparisonSets`) is what left the teacher
      // staring at a blank editor — or at the previous paper, rehydrated from
      // the tab's IndexedDB draft. The review workspace, which is what
      // normally approves, is only reachable with two or more sets, so a
      // single-set request had no route to its own paper at all.
      const sets = [
        ...(setA ? [{ label: "A", result: setA }] : []),
        ...variantSets,
      ];
      if (sets.length > 0) adoptGeneratedSets(sets);
      setPaperSpecHandoff(spec as Record<string, any>);
      if (activeId) void setConversationStatus(activeId, "completed");

      // A beat on the finished sheet before the editor takes over; cutting
      // straight away throws the result off screen before it registers.
      window.setTimeout(() => router.push("/editor"), 1400);
    } catch (error: any) {
      setGeneration(IDLE);
      if (activeId) void setConversationStatus(activeId, "active");
      toast.error(error?.message || "Generation failed.");
    }
  }, [
    activeId,
    canGenerate,
    generation.running,
    router,
    adoptGeneratedSets,
    setPaperSpecHandoff,
    sourceIds,
    spec,
  ]);

  // ── Render ────────────────────────────────────────────────────────────

  if (generation.running) {
    return (
      <div className="flex h-full items-center justify-center overflow-auto p-6">
        <div className="w-full max-w-3xl">
          <PressCheck
            stage={generation.stage}
            status={generation.status}
            rows={generation.rows}
            plannedSlots={generation.plannedSlots}
            poolCount={generation.poolCount}
            sets={generation.sets}
            subject={spec.subject}
            academicClass={spec.academicClass}
            marks={spec.marks}
            done={generation.done}
          />
        </div>
      </div>
    );
  }

  const isEmpty = messages.length === 0 && !streamingText;
  const isPaperSession = mode === "paper";

  const promptBox = (
    <PromptInputBox
      onSend={handleSend}
      onAttach={handleAttach}
      isLoading={isStreaming}
      autoFocus={isEmpty}
      onPickFile={(open) => {
        attachRef.current = open;
      }}
      onStop={() => {
        abortedRef.current = true;
        setIsStreaming(false);
        setStreamingText("");
      }}
    />
  );

  return (
    <PromptTooltipProvider>
      <div className="flex flex-1 min-h-0 w-full">
        <aside
          className={cn(
            "absolute inset-y-0 left-0 z-30 w-64 shrink-0 border-r border-border bg-background",
            "flex flex-col transition-transform duration-200 lg:static lg:translate-x-0",
            sidebarOpen ? "translate-x-0" : "-translate-x-full",
          )}
        >
          <div className="p-3">
            <Button
              variant="outline"
              className="w-full justify-start"
              onClick={startNewSession}
            >
              <MessageSquarePlus className="mr-2 h-4 w-4" />
              New session
            </Button>
          </div>
          <nav className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
            {conversations.map((conversation) => (
              <div
                key={conversation.id}
                className={cn(
                  "group flex items-center gap-1 rounded-lg px-2 py-1.5 text-sm",
                  activeId === conversation.id
                    ? "bg-muted font-medium"
                    : "hover:bg-muted/60",
                )}
              >
                <button
                  onClick={() => loadConversation(conversation.id)}
                  className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
                  title={conversation.title}
                >
                  <span className="truncate">{conversation.title}</span>
                  {conversation.status === "paused" && (
                    <Pause className="h-3 w-3 shrink-0 text-muted-foreground" />
                  )}
                  {conversation.status === "completed" && (
                    <span
                      className="h-1.5 w-1.5 shrink-0 rounded-full bg-primary"
                      title="Paper generated"
                    />
                  )}
                </button>
                <button
                  onClick={() => handleDelete(conversation.id)}
                  aria-label={`Delete ${conversation.title}`}
                  className="shrink-0 rounded-sm p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-foreground/10 hover:text-foreground group-hover:opacity-100"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </nav>
        </aside>

        {sidebarOpen && (
          <div
            className="absolute inset-0 z-20 bg-black/30 lg:hidden"
            onClick={() => setSidebarOpen(false)}
          />
        )}

        {/* `isolate` scopes the backdrop's negative stacking to this column, so
            it sits under the chat but still above the page background — and
            cannot slide behind the sidebar or the mobile scrim. */}
        <div className="relative isolate flex min-h-0 min-w-0 flex-1 flex-col">
          <ChatBackdrop />

          <div className="flex items-center gap-2 border-b border-border px-3 py-2 lg:hidden">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setSidebarOpen(true)}
              aria-label="Show sessions"
            >
              <PanelLeft className="h-4 w-4" />
            </Button>
            <span className="truncate text-sm font-medium">
              {conversations.find((c) => c.id === activeId)?.title ?? "New session"}
            </span>
          </div>

          {isPaperSession && !isEmpty && (
            <SessionHeader
              spec={spec}
              sourceCount={sourceIds.length}
              status={status}
              onPause={() => changeStatus("paused")}
              onResume={() => changeStatus("active")}
            />
          )}

          {isEmpty ? (
            <div className="flex min-h-0 flex-1 flex-col items-center justify-center px-4">
              <div className="w-full max-w-2xl space-y-6">
                <div className="space-y-2 text-center">
                  <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
                    What can I help with?
                  </h1>
                  <p className="text-sm text-muted-foreground">
                    Ask me anything. If it&apos;s a paper you need, I&apos;ll set
                    it up and run the generator for you.
                  </p>
                </div>

                {promptBox}

                <div className="flex flex-wrap justify-center gap-2">
                  {SUGGESTIONS.map((suggestion) => (
                    <button
                      key={suggestion}
                      onClick={() => handleSend(suggestion, [])}
                      className="rounded-full border border-border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-foreground/25 hover:text-foreground"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <>
              <div
                ref={scrollRef}
                className="min-h-0 flex-1 overflow-y-auto px-4 py-6"
              >
                <div className="mx-auto flex max-w-2xl flex-col gap-4">
                  {messages.map((message) => (
                    <MessageBubble key={message.id} message={message} />
                  ))}

                  {streamingText && (
                    <MessageBubble
                      message={{
                        id: "streaming",
                        role: "assistant",
                        content: streamingText,
                      }}
                    />
                  )}
                  {isStreaming && !streamingText && (
                    <div className="flex justify-start">
                      <TypingDots />
                    </div>
                  )}

                  {prompt && !isStreaming && status !== "paused" && (
                    <FollowUpCard
                      prompt={prompt}
                      onAnswer={(text) => handleSend(text, [])}
                      onAttach={() => attachRef.current?.()}
                    />
                  )}

                  {/* A structure described in the teacher's own words gets
                      shown back to them before three minutes are spent on it,
                      along with anything it left open. */}
                  {customInstructions && !isStreaming && (
                    <PaperDesignPanel
                      design={paperDesign.design}
                      gaps={paperDesign.gaps}
                      loading={paperDesign.loading}
                      onResolve={resolveDesignGap}
                      sourceAction={
                        <p className="mt-1.5 text-[11px] text-muted-foreground">
                          Attach the chapter PDF with the paperclip below.
                        </p>
                      }
                    />
                  )}

                  {readyToGenerate && !isStreaming && (
                    <div className="rounded-2xl border border-primary/30 bg-primary/5 p-4">
                      <div className="flex items-center gap-2">
                        <h3 className="text-sm font-semibold">
                          Everything&apos;s set
                        </h3>
                      </div>
                      <p className="mt-1.5 text-sm text-muted-foreground">
                        {resolvedSpec.subject} · Class{" "}
                        {resolvedSpec.academicClass} ·{" "}
                        {customInstructions && paperDesign.design
                          ? `${paperDesign.design.totalMarks} marks`
                          : `${spec.marks} marks`}{" "}
                        · {sourceIds.length} source
                        {sourceIds.length === 1 ? "" : "s"}. This takes three to
                        four minutes.
                      </p>
                      <Button onClick={handleGenerate} className="mt-3" size="sm">
                        Generate the paper
                        <ArrowRight className="ml-1.5 h-4 w-4" />
                      </Button>
                    </div>
                  )}
                </div>
              </div>

              <div className="border-t border-border px-4 py-3">
                <div className="mx-auto max-w-2xl">{promptBox}</div>
              </div>
            </>
          )}
        </div>
      </div>
    </PromptTooltipProvider>
  );
}
