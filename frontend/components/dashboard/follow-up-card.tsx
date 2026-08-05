"use client";

/**
 * The assistant's question, as something you tap rather than type.
 *
 * Every field the generator takes has a closed set of answers, so the backend
 * derives this widget from the spec (`services/chat_service.py::next_prompt`)
 * instead of letting the model invent one. The model's prose asks the
 * question; this is the same question with the answers attached.
 *
 * Answering posts an ordinary message ("Subject: Science"). That matters: the
 * transcript stays the single source of truth, so a tapped answer and a typed
 * one are indistinguishable afterwards — including to the extraction pass
 * that rebuilds the spec.
 */

import * as React from "react";
import { motion } from "framer-motion";
import { Paperclip, SkipForward } from "lucide-react";

import { cn } from "@/lib/utils";
import type { FollowUpPrompt } from "@/lib/api-client";

export interface FollowUpCardProps {
  prompt: FollowUpPrompt;
  onAnswer: (text: string) => void;
  onAttach: () => void;
  disabled?: boolean;
}

export function FollowUpCard({
  prompt,
  onAnswer,
  onAttach,
  disabled,
}: FollowUpCardProps) {
  const [other, setOther] = React.useState("");

  const submitOther = () => {
    const value = other.trim();
    if (!value) return;
    onAnswer(`${prompt.label} ${value}`);
    setOther("");
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className="rounded-2xl border border-border bg-muted/40 p-4"
    >
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-sm font-medium">{prompt.label}</p>
        {prompt.optional && (
          <button
            type="button"
            disabled={disabled}
            onClick={() => onAnswer("Skip that — use a sensible default.")}
            className="flex shrink-0 items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground disabled:opacity-50"
          >
            <SkipForward className="h-3 w-3" />
            Skip
          </button>
        )}
      </div>

      {prompt.hint && (
        <p className="mt-1 text-xs text-muted-foreground">{prompt.hint}</p>
      )}

      {prompt.kind === "choice" && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {(prompt.options ?? []).map((option) => (
            <button
              key={option.value}
              type="button"
              disabled={disabled}
              onClick={() => onAnswer(`${prompt.label} ${option.label}`)}
              className={cn(
                "group flex items-baseline gap-1.5 rounded-lg border border-border bg-background",
                "px-3 py-1.5 text-sm transition-colors",
                "hover:border-primary hover:bg-primary/5",
                "disabled:cursor-not-allowed disabled:opacity-50",
              )}
            >
              <span>{option.label}</span>
              {option.hint && (
                <span className="text-xs text-muted-foreground">
                  {option.hint}
                </span>
              )}
            </button>
          ))}
        </div>
      )}

      {prompt.kind === "files" && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          <button
            type="button"
            disabled={disabled}
            onClick={onAttach}
            className="flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-sm transition-colors hover:border-primary hover:bg-primary/5 disabled:opacity-50"
          >
            <Paperclip className="h-3.5 w-3.5" />
            Attach a PDF
          </button>
        </div>
      )}

      {(prompt.kind === "text" || prompt.allowOther) && (
        <div className="mt-2.5 flex gap-1.5">
          <input
            value={other}
            disabled={disabled}
            onChange={(event) => setOther(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                submitOther();
              }
            }}
            placeholder={prompt.kind === "text" ? "Type your answer" : "Or something else"}
            aria-label={prompt.label}
            className="min-w-0 flex-1 rounded-lg border border-border bg-background px-3 py-1.5 text-sm outline-none transition-colors focus:border-primary disabled:opacity-50"
          />
          <button
            type="button"
            disabled={disabled || !other.trim()}
            onClick={submitOther}
            className="rounded-lg border border-border bg-background px-3 py-1.5 text-sm transition-colors hover:border-primary disabled:opacity-40"
          >
            Use
          </button>
        </div>
      )}
    </motion.div>
  );
}
