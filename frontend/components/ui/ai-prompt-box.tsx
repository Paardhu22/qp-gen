"use client";

/**
 * The dashboard assistant's input box.
 *
 * Adapted from a Radix-based reference component. Three things changed on the
 * way in, all of them load-bearing:
 *
 * 1. Primitives are `@base-ui/react`, not Radix. This project's shadcn style
 *    is `base-nova` and every other `components/ui/*` file is built on base-ui;
 *    pulling in `@radix-ui/react-dialog` and `@radix-ui/react-tooltip` would
 *    have shipped a second, parallel primitive library for one component.
 * 2. Colours are theme tokens, not hardcoded `#1F2023`. The reference assumed
 *    a permanently dark page; this app has a light/dark toggle.
 * 3. The reference injected a `<style>` element at module scope. That runs on
 *    import — during SSR, where `document` does not exist — and would crash
 *    the route. The two rules it carried are inlined below via Tailwind
 *    instead, so nothing has to touch the DOM before mount.
 *
 * The Search / Think / Canvas toggles and the voice recorder from the
 * reference are gone: none had a backing capability (the recorder captured no
 * audio and sent a `[Voice message - 12 seconds]` string), and a control that
 * does nothing reads as a bug to a teacher. The paperclip stayed, repurposed
 * to accept the PDFs this app already ingests.
 */

import * as React from "react";
import { Tooltip as TooltipPrimitive } from "@base-ui/react/tooltip";
import { ArrowUp, Paperclip, Square, X, FileText } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

import { cn } from "@/lib/utils";

export interface PromptAttachment {
  id: string;
  name: string;
  size?: number;
}

// ── Tooltip ─────────────────────────────────────────────────────────────

function IconTooltip({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <TooltipPrimitive.Root>
      <TooltipPrimitive.Trigger render={<span className="inline-flex" />}>
        {children}
      </TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Positioner sideOffset={8}>
          <TooltipPrimitive.Popup className="z-50 rounded-md bg-popover px-2.5 py-1.5 text-xs text-popover-foreground ring-1 ring-foreground/10 shadow-md data-open:animate-in data-open:fade-in-0 data-open:zoom-in-95 data-closed:animate-out data-closed:fade-out-0">
            {label}
          </TooltipPrimitive.Popup>
        </TooltipPrimitive.Positioner>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}

export const PromptTooltipProvider = TooltipPrimitive.Provider;

// ── Attachment chips ────────────────────────────────────────────────────

function AttachmentChip({
  attachment,
  onRemove,
  disabled,
}: {
  attachment: PromptAttachment;
  onRemove: () => void;
  disabled?: boolean;
}) {
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4 }}
      transition={{ duration: 0.15 }}
      className="flex items-center gap-2 rounded-lg border border-border bg-muted/60 py-1.5 pr-1.5 pl-2.5 text-xs"
    >
      <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
      <span className="max-w-[180px] truncate font-medium">
        {attachment.name}
      </span>
      {!disabled && (
        <button
          type="button"
          onClick={onRemove}
          className="rounded-full p-0.5 text-muted-foreground transition-colors hover:bg-foreground/10 hover:text-foreground"
          aria-label={`Remove ${attachment.name}`}
        >
          <X className="h-3 w-3" />
        </button>
      )}
    </motion.div>
  );
}

// ── The box ─────────────────────────────────────────────────────────────

export interface PromptInputBoxProps {
  onSend: (message: string, attachments: PromptAttachment[]) => void;
  /** A reply is streaming; the send button becomes a stop button. */
  isLoading?: boolean;
  onStop?: () => void;
  /** Called when a file is picked. Resolve with the ingested source, or null to reject it. */
  onAttach?: (file: File) => Promise<PromptAttachment | null>;
  /**
   * Hands the caller a function that opens the file picker.
   *
   * The assistant's "attach the chapters" follow-up card is rendered up in the
   * transcript, but the only `<input type="file">` lives down here. Rather
   * than give the card a second input — and a second place for the accept
   * list and the upload handler to drift — it borrows this one.
   */
  onPickFile?: (open: () => void) => void;
  placeholder?: string;
  disabled?: boolean;
  autoFocus?: boolean;
  className?: string;
}

const MAX_TEXTAREA_HEIGHT = 220;

export function PromptInputBox({
  onSend,
  isLoading = false,
  onStop,
  onAttach,
  onPickFile,
  placeholder = "Ask me anything, or describe the paper you need…",
  disabled = false,
  autoFocus = false,
  className,
}: PromptInputBoxProps) {
  const [input, setInput] = React.useState("");
  const [attachments, setAttachments] = React.useState<PromptAttachment[]>([]);
  const [isUploading, setIsUploading] = React.useState(false);
  const [isDragging, setIsDragging] = React.useState(false);

  const textareaRef = React.useRef<HTMLTextAreaElement>(null);
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  // Autosize. Reset to "auto" first or the box can only ever grow.
  React.useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_TEXTAREA_HEIGHT)}px`;
  }, [input]);

  const hasContent = input.trim().length > 0 || attachments.length > 0;
  const isBusy = disabled || isUploading;

  React.useEffect(() => {
    onPickFile?.(() => fileInputRef.current?.click());
  }, [onPickFile]);

  // Files are taken as a batch and ingested together: a teacher attaching
  // three chapters should pick them once, and should not wait for chapter one
  // to finish processing before chapter two starts.
  const handleFiles = React.useCallback(
    async (files: File[]) => {
      if (!onAttach || files.length === 0) return;
      setIsUploading(true);
      try {
        const results = await Promise.all(files.map((file) => onAttach(file)));
        const accepted = results.filter(
          (result): result is PromptAttachment => Boolean(result),
        );
        if (accepted.length > 0) {
          // De-duplicate on id so the same PDF attached twice — which the
          // backend dedupes to one source — does not show as two chips.
          setAttachments((current) => {
            const seen = new Set(current.map((a) => a.id));
            return [...current, ...accepted.filter((a) => !seen.has(a.id))];
          });
        }
      } finally {
        setIsUploading(false);
      }
    },
    [onAttach],
  );

  const handleSubmit = React.useCallback(() => {
    if (!hasContent || isLoading || isBusy) return;
    onSend(input.trim(), attachments);
    setInput("");
    setAttachments([]);
  }, [attachments, hasContent, input, isBusy, isLoading, onSend]);

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter sends, Shift+Enter breaks the line. IME composition must be left
    // alone or a Hindi/Telugu candidate selection would submit the message.
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div
      onDragOver={(event) => {
        if (!onAttach) return;
        event.preventDefault();
        setIsDragging(true);
      }}
      onDragLeave={(event) => {
        event.preventDefault();
        setIsDragging(false);
      }}
      onDrop={(event) => {
        if (!onAttach) return;
        event.preventDefault();
        setIsDragging(false);
        void handleFiles(Array.from(event.dataTransfer.files ?? []));
      }}
      className={cn(
        "rounded-3xl border border-border bg-card p-2 shadow-sm transition-colors duration-200",
        "focus-within:border-foreground/25",
        isDragging && "border-primary bg-primary/5",
        className,
      )}
    >
      <AnimatePresence initial={false}>
        {attachments.length > 0 && (
          <motion.div
            layout
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="flex flex-wrap gap-2 overflow-hidden px-1 pt-1 pb-2"
          >
            {attachments.map((attachment, index) => (
              <AttachmentChip
                key={attachment.id}
                attachment={attachment}
                disabled={isLoading}
                onRemove={() =>
                  setAttachments((current) =>
                    current.filter((_, i) => i !== index),
                  )
                }
              />
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      <textarea
        ref={textareaRef}
        rows={1}
        autoFocus={autoFocus}
        value={input}
        onChange={(event) => setInput(event.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder={placeholder}
        aria-label="Message the assistant"
        className={cn(
          "min-h-[44px] w-full resize-none border-none bg-transparent px-3 py-2.5",
          "text-base text-foreground placeholder:text-muted-foreground",
          "focus-visible:ring-0 focus-visible:outline-none",
          "disabled:cursor-not-allowed disabled:opacity-50",
          // Replaces the reference component's injected ::-webkit-scrollbar
          // rules, which it appended to <head> at module scope.
          "[scrollbar-width:thin] [&::-webkit-scrollbar]:w-1.5",
          "[&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-foreground/20",
          "[&::-webkit-scrollbar-track]:bg-transparent",
        )}
      />

      <div className="flex items-center justify-between gap-2 px-1 pt-2">
        <div className="flex items-center gap-1">
          {onAttach && (
            <IconTooltip
              label={isUploading ? "Reading your PDFs…" : "Attach PDFs"}
            >
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={isBusy || isLoading}
                aria-label="Attach PDFs"
                className={cn(
                  "flex h-8 w-8 items-center justify-center rounded-full",
                  "text-muted-foreground transition-colors",
                  "hover:bg-foreground/5 hover:text-foreground",
                  "disabled:cursor-not-allowed disabled:opacity-50",
                )}
              >
                <Paperclip
                  className={cn("h-5 w-5", isUploading && "animate-pulse")}
                />
              </button>
            </IconTooltip>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept="application/pdf,.pdf"
            multiple
            className="hidden"
            onChange={(event) => {
              void handleFiles(Array.from(event.target.files ?? []));
              // Clear so picking the same file twice still fires onChange.
              event.target.value = "";
            }}
          />
        </div>

        <IconTooltip
          label={isLoading ? "Stop generating" : "Send message"}
        >
          <button
            type="button"
            onClick={() => {
              if (isLoading) onStop?.();
              else handleSubmit();
            }}
            disabled={isLoading ? !onStop : !hasContent || isBusy}
            aria-label={isLoading ? "Stop generating" : "Send message"}
            className={cn(
              "flex h-8 w-8 items-center justify-center rounded-full transition-colors",
              isLoading
                ? "bg-foreground/10 text-foreground hover:bg-foreground/20"
                : hasContent
                  ? "bg-primary text-primary-foreground hover:bg-primary/90"
                  : "bg-transparent text-muted-foreground",
              "disabled:cursor-not-allowed disabled:opacity-50",
            )}
          >
            {isLoading ? (
              <Square className="h-3.5 w-3.5 fill-current" />
            ) : (
              <ArrowUp className="h-4 w-4" />
            )}
          </button>
        </IconTooltip>
      </div>
    </div>
  );
}
