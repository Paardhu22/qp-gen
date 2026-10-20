"use client";

import { useEffect, useState } from "react";

import { getPaperAction } from "@/features/papers/actions/savePaper";

import { extractQuestionPreview, type PreviewQuestion } from "./question-preview";

export type PreviewState =
  | { status: "idle" | "loading" }
  | { status: "ready"; questions: PreviewQuestion[] }
  | { status: "error" };

/**
 * The list endpoint carries no question content on purpose (it is large), so
 * a card's preview is fetched when the card scrolls into view. Results are
 * cached per paper + `updated_at`, so re-sorting, filtering and coming back
 * from the detail view cost nothing, and an edited paper refreshes itself.
 *
 * Requests go through a small queue: a library of forty papers must not fire
 * forty full-paper fetches at once and starve the detail request a teacher
 * actually clicked.
 */
const cache = new Map<string, PreviewQuestion[] | "error">();
const MAX_IN_FLIGHT = 3;
let inFlight = 0;
const waiting: (() => void)[] = [];

function acquire(): Promise<void> {
  if (inFlight < MAX_IN_FLIGHT) {
    inFlight += 1;
    return Promise.resolve();
  }
  return new Promise((resolve) => waiting.push(resolve));
}

function release() {
  const next = waiting.shift();
  if (next) next();
  else inFlight -= 1;
}

async function load(paperId: string, key: string): Promise<void> {
  await acquire();
  try {
    const paper = await getPaperAction(paperId);
    cache.set(key, extractQuestionPreview(paper.content));
  } catch {
    cache.set(key, "error");
  } finally {
    release();
  }
}

const pending = new Map<string, Promise<void>>();

export function usePaperPreview(
  paperId: string,
  updatedAt: string | undefined,
  enabled: boolean,
): PreviewState {
  const key = `${paperId}:${updatedAt ?? ""}`;
  const [, bump] = useState(0);

  useEffect(() => {
    if (!enabled || cache.has(key)) return;
    let active = true;
    let request = pending.get(key);
    if (!request) {
      request = load(paperId, key).finally(() => pending.delete(key));
      pending.set(key, request);
    }
    void request.then(() => active && bump((n) => n + 1));
    return () => {
      active = false;
    };
  }, [enabled, key, paperId]);

  const hit = cache.get(key);
  if (hit === "error") return { status: "error" };
  if (hit) return { status: "ready", questions: hit };
  return { status: enabled ? "loading" : "idle" };
}
