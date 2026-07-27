"use client";

/**
 * The dashboard is the assistant.
 *
 * It replaced a Quick Start / Overview & Stats / Recent Papers board. The
 * generator form asks a teacher to answer eleven fields before it will do
 * anything; this asks them to say what they want and fills the form in for
 * them. When the requirements are settled the conversation hands off to the
 * real pipeline — the model here never writes a question itself.
 */

import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  ArrowRight,
  MessageSquarePlus,
  PanelLeft,
  Sparkles,
  Trash2,
} from "lucide-react";

import {
  PromptInputBox,
  PromptTooltipProvider,
  type PromptAttachment,
} from "@/components/ui/ai-prompt-box";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useEditorStore } from "@/store/editor-store";
import {
  createConversation,
  deleteConversation,
  fetchConversation,
  fetchConversations,
  streamChatMessage,
  uploadPdfSource,
  type ChatMessage,
  type Conversation,
  type PaperSpec,
} from "@/lib/api-client";

const SUGGESTIONS = [
  "I need a class 10 Science unit test on Light and Electricity.",
  "Make me an 80-mark CBSE class 10 Maths board-pattern paper.",
  "What does the class 10 English paper look like this year?",
  "Build a 40-mark Social Science test, three parallel sets.",
];

const SPEC_LABELS: Array<[keyof PaperSpec, string]> = [
  ["board", "Board"],
  ["academicClass", "Class"],
  ["subject", "Subject"],
  ["marks", "Marks"],
  ["difficulty", "Difficulty"],
  ["numberOfQuestions", "Questions"],
  ["numberOfSets", "Sets"],
];

function specValue(spec: PaperSpec, key: keyof PaperSpec): string {
  const value = spec[key];
  if (Array.isArray(value)) return value.join(", ");
  return String(value ?? "");
}

// ── Message bubbles ─────────────────────────────────────────────────────

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={cn("flex w-full", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-foreground",
        )}
      >
        {/* Plain text, deliberately: the assistant is instructed to answer in
            prose, and rendering model output as HTML would be an injection
            surface for no gain. `whitespace-pre-wrap` keeps its line breaks. */}
        <p className="whitespace-pre-wrap break-words">{message.content}</p>
        {(message.attachments?.length ?? 0) > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {message.attachments!.map((attachment) => (
              <span
                key={attachment.id}
                className={cn(
                  "rounded-md px-2 py-0.5 text-xs",
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

// ── Spec handoff card ───────────────────────────────────────────────────

function SpecCard({ spec, onGenerate }: { spec: PaperSpec; onGenerate: () => void }) {
  const filled = SPEC_LABELS.filter(([key]) => specValue(spec, key));
  const chapters = spec.chapters?.length ? spec.chapters.join(", ") : "";

  return (
    <div className="rounded-2xl border border-primary/30 bg-primary/5 p-4">
      <div className="flex items-center gap-2">
        <Sparkles className="h-4 w-4 text-primary" />
        <h3 className="text-sm font-semibold">Ready to generate</h3>
      </div>
      <dl className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5 text-sm">
        {filled.map(([key, label]) => (
          <div key={key} className="flex items-baseline gap-1.5">
            <dt className="text-xs text-muted-foreground">{label}</dt>
            <dd className="font-medium">{specValue(spec, key)}</dd>
          </div>
        ))}
        {chapters && (
          <div className="flex items-baseline gap-1.5">
            <dt className="text-xs text-muted-foreground">Chapters</dt>
            <dd className="font-medium">{chapters}</dd>
          </div>
        )}
      </dl>
      <Button onClick={onGenerate} className="mt-4" size="sm">
        Generate this paper
        <ArrowRight className="ml-1.5 h-4 w-4" />
      </Button>
    </div>
  );
}

// ── Page ────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const router = useRouter();
  const setPaperSpecHandoff = useEditorStore((s) => s.setPaperSpecHandoff);

  const [conversations, setConversations] = React.useState<Conversation[]>([]);
  const [activeId, setActiveId] = React.useState<string | null>(null);
  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [spec, setSpec] = React.useState<PaperSpec>({});
  const [specReady, setSpecReady] = React.useState(false);
  const [streamingText, setStreamingText] = React.useState("");
  const [isStreaming, setIsStreaming] = React.useState(false);
  const [sidebarOpen, setSidebarOpen] = React.useState(false);

  const scrollRef = React.useRef<HTMLDivElement>(null);
  // Streaming writes on every token; a ref keeps the abort check out of the
  // render path so an aborted turn stops appending immediately.
  const abortedRef = React.useRef(false);

  React.useEffect(() => {
    fetchConversations()
      .then(setConversations)
      .catch(() => {
        /* An empty history is a valid first-run state, not an error to show. */
      });
  }, []);

  // Pin to the newest message as tokens arrive.
  React.useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, streamingText]);

  const loadConversation = React.useCallback(async (conversationId: string) => {
    try {
      const detail = await fetchConversation(conversationId);
      setActiveId(detail.id);
      setMessages(detail.messages || []);
      setSpec(detail.spec || {});
      setSpecReady(
        Boolean(
          detail.spec?.board &&
            detail.spec?.academicClass &&
            detail.spec?.subject &&
            detail.spec?.marks,
        ),
      );
      setSidebarOpen(false);
    } catch {
      toast.error("Could not open that conversation.");
    }
  }, []);

  const startNewChat = React.useCallback(() => {
    setActiveId(null);
    setMessages([]);
    setSpec({});
    setSpecReady(false);
    setStreamingText("");
    setSidebarOpen(false);
  }, []);

  const handleDelete = React.useCallback(
    async (conversationId: string) => {
      try {
        await deleteConversation(conversationId);
        setConversations((current) =>
          current.filter((c) => c.id !== conversationId),
        );
        if (activeId === conversationId) startNewChat();
      } catch {
        toast.error("Could not delete that conversation.");
      }
    },
    [activeId, startNewChat],
  );

  const handleAttach = React.useCallback(
    async (file: File): Promise<PromptAttachment | null> => {
      if (file.type !== "application/pdf") {
        toast.error("Only PDF files can be attached.");
        return null;
      }
      try {
        const { pdfSourceId, warnings } = await uploadPdfSource(file);
        warnings?.forEach((w) => toast.warning(w, { duration: 8000 }));
        return { id: pdfSourceId, name: file.name, size: file.size };
      } catch {
        toast.error("Could not upload that PDF.");
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
          toast.error("Could not start a conversation.");
          return;
        }
      }

      // Optimistic: the teacher's own turn should appear the instant they
      // send it, not a round trip later. The id is local-only and is replaced
      // when the conversation is next loaded from the server.
      setMessages((current) => [
        ...current,
        {
          id: `local-${Date.now()}`,
          role: "user",
          content,
          attachments,
        },
      ]);
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
              setSpecReady(Boolean(data.ready));
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
          // Keep whatever streamed before the connection dropped: the teacher
          // already read it, and the backend has persisted the same text.
          if (assembled) {
            setMessages((current) => [
              ...current,
              {
                id: `partial-${Date.now()}`,
                role: "assistant",
                content: assembled,
              },
            ]);
          }
          setStreamingText("");
        }
      } finally {
        setIsStreaming(false);
        // The title is derived from the first turn, so refresh the list once
        // the exchange lands rather than showing "New chat" until reload.
        fetchConversations().then(setConversations).catch(() => {});
      }
    },
    [activeId],
  );

  const handleGenerate = React.useCallback(() => {
    setPaperSpecHandoff(spec);
    router.push("/editor?new=true");
  }, [router, setPaperSpecHandoff, spec]);

  const isEmpty = messages.length === 0 && !streamingText;

  return (
    <PromptTooltipProvider>
      <div className="flex h-full min-h-0 w-full">
        {/* History */}
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
              onClick={startNewChat}
            >
              <MessageSquarePlus className="mr-2 h-4 w-4" />
              New chat
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
                  className="min-w-0 flex-1 truncate text-left"
                  title={conversation.title}
                >
                  {conversation.title}
                </button>
                <button
                  onClick={() => handleDelete(conversation.id)}
                  aria-label={`Delete ${conversation.title}`}
                  className="shrink-0 rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-foreground/10 hover:text-foreground group-hover:opacity-100"
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

        {/* Conversation */}
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <div className="flex items-center gap-2 border-b border-border px-3 py-2 lg:hidden">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setSidebarOpen(true)}
              aria-label="Show conversations"
            >
              <PanelLeft className="h-4 w-4" />
            </Button>
            <span className="truncate text-sm font-medium">
              {conversations.find((c) => c.id === activeId)?.title ?? "New chat"}
            </span>
          </div>

          {isEmpty ? (
            <div className="flex min-h-0 flex-1 flex-col items-center justify-center px-4">
              <div className="w-full max-w-2xl space-y-6">
                <div className="space-y-2 text-center">
                  <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
                    What paper do you need?
                  </h1>
                  <p className="text-sm text-muted-foreground">
                    Describe it in your own words. I&apos;ll ask for anything
                    missing and set up the generator for you.
                  </p>
                </div>

                <PromptInputBox
                  onSend={handleSend}
                  onAttach={handleAttach}
                  isLoading={isStreaming}
                  autoFocus
                />

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

                  {specReady && !isStreaming && (
                    <SpecCard spec={spec} onGenerate={handleGenerate} />
                  )}
                </div>
              </div>

              <div className="border-t border-border px-4 py-3">
                <div className="mx-auto max-w-2xl">
                  <PromptInputBox
                    onSend={handleSend}
                    onAttach={handleAttach}
                    isLoading={isStreaming}
                    onStop={() => {
                      abortedRef.current = true;
                      setIsStreaming(false);
                      setStreamingText("");
                    }}
                  />
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </PromptTooltipProvider>
  );
}
