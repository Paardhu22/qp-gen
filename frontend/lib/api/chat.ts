/** The dashboard assistant: conversations and streamed replies. */
"use client";

import { fetchJson } from "@/lib/api/http";
import { SseEventHandler, streamSse } from "@/lib/api/sse";

/** Field names match `formSchema` in components/generator-form.tsx. */
export interface PaperSpec {
  board?: string;
  academicClass?: string;
  subject?: string;
  difficulty?: string;
  marks?: string;
  numberOfQuestions?: string;
  numberOfSets?: string;
  chapters?: string[];
  /**
   * A paper structure the teacher described in their own words ("5 MCQs and
   * 3 short answers", "same as our weekly test"). Its presence switches
   * generation from the CBSE blueprint to General Instructions Mode, where
   * `services/paper_design.py` lays the paper out from this text alone.
   */
  instructions?: string;
}

export interface ChatAttachment {
  id: string;
  name: string;
  size?: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  attachments?: ChatAttachment[];
  created_at?: string;
}

/** What the interface should put in front of the teacher next. */
export interface FollowUpPrompt {
  field: string;
  kind: "choice" | "files" | "text";
  label: string;
  hint?: string;
  optional?: boolean;
  allowOther?: boolean;
  options?: { value: string; label: string; hint?: string }[];
}

export type ConversationMode = "chat" | "paper";

export type ConversationStatus =
  | "active"
  | "paused"
  | "generating"
  | "completed";

export interface Conversation {
  id: string;
  title: string;
  spec: PaperSpec;
  mode: ConversationMode;
  status: ConversationStatus;
  paper_id?: string | null;
  ready: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface ConversationDetail extends Conversation {
  messages: ChatMessage[];
  next_prompt: FollowUpPrompt | null;
  /** Every PDF attached across the session — what generation reads from. */
  source_ids: string[];
  /**
   * Whether pressing Generate would actually succeed. Stricter than `ready`:
   * the blueprint needs four fields, but the pipeline also needs a source.
   */
  can_generate: boolean;
}

export async function setConversationStatus(
  conversationId: string,
  status: ConversationStatus,
  paperId?: string,
): Promise<Conversation> {
  return fetchJson<Conversation>(
    `/api/chat/conversations/${conversationId}/status`,
    {
      method: "POST",
      body: JSON.stringify({ status, ...(paperId ? { paperId } : {}) }),
    },
  );
}

export async function fetchConversations(): Promise<Conversation[]> {
  return fetchJson<Conversation[]>("/api/chat/conversations", { method: "GET" });
}

export async function fetchConversation(
  conversationId: string,
): Promise<ConversationDetail> {
  return fetchJson<ConversationDetail>(
    `/api/chat/conversations/${conversationId}`,
    { method: "GET" },
  );
}

export async function createConversation(): Promise<ConversationDetail> {
  return fetchJson<ConversationDetail>("/api/chat/conversations", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function deleteConversation(conversationId: string): Promise<void> {
  await fetchJson<void>(`/api/chat/conversations/${conversationId}`, {
    method: "DELETE",
  });
}

export async function renameConversation(
  conversationId: string,
  title: string,
): Promise<Conversation> {
  return fetchJson<Conversation>(`/api/chat/conversations/${conversationId}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });
}

/**
 * Stream one assistant turn.
 *
 * Events: `delta` ({text}) per token, `spec` ({spec, ready}) once the reply is
 * complete, then the terminal `done` — or `error`. `streamSse` throws if the
 * connection closes before a terminal event, so a proxy timeout surfaces as a
 * failure rather than a silently truncated reply.
 */
export async function streamChatMessage(
  conversationId: string,
  content: string,
  attachments: ChatAttachment[],
  onEvent: SseEventHandler,
): Promise<void> {
  return streamSse(
    `/api/chat/conversations/${conversationId}/messages`,
    { content, attachments },
    onEvent,
  );
}
