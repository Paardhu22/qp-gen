"use client";

/**
 * Step 2 of the Blueprint Builder — where the questions come from.
 *
 * "Apply Source from HSAT" used to be a button in the editor toolbar, parallel
 * to the upload control in the sidebar, which made two things that are the
 * same thing look different: both end up as `DocumentChunk` rows that Model 1
 * reads. Here they are two ways to answer one question — *which chapters?* —
 * and the picker opens from inside this panel rather than from the chrome.
 *
 * Sources are optional on purpose. A paper whose slots all come from the bank
 * needs none, and an English paper's Reading and Writing sections are written
 * by generators that never see an upload. The panel says so rather than
 * blocking, because a teacher who is told "upload something" for a paper that
 * does not need one has been told something false.
 */

import * as React from "react";
import {
  CheckCircle2,
  FileText,
  Library,
  Loader2,
  Upload,
  X,
  AlertCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { AppliedHsatSource } from "@/components/hsat-source-picker";

export interface UploadedDoc {
  id: string;
  name: string;
  size: number;
}

export interface UploadingDoc {
  tempId: string;
  name: string;
  status: "uploading" | "processing" | "error";
  error?: string;
  pdfSourceId?: string;
  size?: number;
}

interface Props {
  uploadedDocs: UploadedDoc[];
  uploadingDocs: UploadingDoc[];
  hsatSources: AppliedHsatSource[];
  /** Slots set to draw from the bank — shown so "no sources" reads as fine. */
  savedCount: number;
  onFiles: (files: File[]) => void;
  onRemoveDoc: (id: string) => void;
  onDismissUpload: (tempId: string) => void;
  onRemoveHsat: (id: string) => void;
  onOpenHsatPicker: () => void;
}

function formatSize(bytes?: number) {
  if (!bytes) return "";
  const mb = bytes / (1024 * 1024);
  return mb >= 1 ? `${mb.toFixed(1)} MB` : `${Math.round(bytes / 1024)} KB`;
}

function SourceRow({
  icon: Icon,
  title,
  subtitle,
  tone = "default",
  onRemove,
  removeLabel,
}: {
  icon: React.ElementType;
  title: string;
  subtitle?: string;
  tone?: "default" | "busy" | "error";
  onRemove?: () => void;
  removeLabel: string;
}) {
  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-lg border px-3 py-2.5",
        tone === "error"
          ? "border-destructive/40 bg-destructive/5"
          : "border-border bg-card",
      )}
    >
      <Icon
        className={cn(
          "size-4 shrink-0",
          tone === "busy" && "animate-spin",
          tone === "error" ? "text-destructive" : "text-muted-foreground",
        )}
      />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium leading-tight">{title}</p>
        {subtitle ? (
          <p
            className={cn(
              "truncate text-xs",
              tone === "error" ? "text-destructive" : "text-muted-foreground",
            )}
          >
            {subtitle}
          </p>
        ) : null}
      </div>
      {onRemove ? (
        <button
          type="button"
          aria-label={removeLabel}
          onClick={onRemove}
          className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <X className="size-3.5" />
        </button>
      ) : null}
    </div>
  );
}

export function SourcePanel({
  uploadedDocs,
  uploadingDocs,
  hsatSources,
  savedCount,
  onFiles,
  onRemoveDoc,
  onDismissUpload,
  onRemoveHsat,
  onOpenHsatPicker,
}: Props) {
  const [dragging, setDragging] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);

  const hasAnySource =
    uploadedDocs.length > 0 || uploadingDocs.length > 0 || hsatSources.length > 0;

  const handleFiles = (list: FileList | null) => {
    if (!list || list.length === 0) return;
    onFiles(Array.from(list));
  };

  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2">
        {/* Upload */}
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            handleFiles(e.dataTransfer.files);
          }}
          onClick={() => inputRef.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              inputRef.current?.click();
            }
          }}
          className={cn(
            "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-6 text-center transition-colors",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
            dragging
              ? "border-primary bg-primary/5"
              : "border-border hover:border-primary/40 hover:bg-muted/40",
          )}
        >
          <span className="flex size-10 items-center justify-center rounded-full bg-muted">
            <Upload className="size-4 text-muted-foreground" />
          </span>
          <div>
            <p className="text-sm font-semibold">Upload a chapter</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Drop a PDF or Word file, or click to browse
            </p>
          </div>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept=".pdf,.docx,.doc,.txt"
            className="hidden"
            onChange={(e) => {
              handleFiles(e.target.files);
              // Reset so re-picking the same file fires change again.
              e.target.value = "";
            }}
          />
        </div>

        {/* HSAT library */}
        <div
          onClick={onOpenHsatPicker}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              onOpenHsatPicker();
            }
          }}
          className={cn(
            "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-border p-6 text-center transition-colors",
            "hover:border-primary/40 hover:bg-muted/40",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
          )}
        >
          <span className="flex size-10 items-center justify-center rounded-full bg-muted">
            <Library className="size-4 text-muted-foreground" />
          </span>
          <div>
            <p className="text-sm font-semibold">Choose from the library</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              NCERT textbooks, already prepared — no upload needed
            </p>
          </div>
        </div>
      </div>

      {hasAnySource ? (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Selected sources
          </h4>

          {hsatSources.map((source) => (
            <SourceRow
              key={source.id}
              icon={source.status === "ready" ? CheckCircle2 : Loader2}
              tone={source.status === "ready" ? "default" : "busy"}
              title={source.book}
              subtitle={
                source.status === "ready"
                  ? `Class ${source.grade} ${source.subject}${
                      source.selectedChapterCount
                        ? ` · ${source.selectedChapterCount} chapter${source.selectedChapterCount === 1 ? "" : "s"}`
                        : ""
                    }`
                  : "Preparing this book…"
              }
              onRemove={() => onRemoveHsat(source.id)}
              removeLabel={`Remove ${source.book}`}
            />
          ))}

          {uploadedDocs.map((doc) => (
            <SourceRow
              key={doc.id}
              icon={CheckCircle2}
              title={doc.name}
              subtitle={`Ready · ${formatSize(doc.size)}`}
              onRemove={() => onRemoveDoc(doc.id)}
              removeLabel={`Remove ${doc.name}`}
            />
          ))}

          {uploadingDocs.map((doc) => (
            <SourceRow
              key={doc.tempId}
              icon={doc.status === "error" ? AlertCircle : Loader2}
              tone={doc.status === "error" ? "error" : "busy"}
              title={doc.name}
              subtitle={
                doc.status === "error"
                  ? doc.error || "Upload failed"
                  : doc.status === "uploading"
                    ? "Uploading…"
                    : "Reading the chapter…"
              }
              onRemove={
                doc.status === "error"
                  ? () => onDismissUpload(doc.tempId)
                  : undefined
              }
              removeLabel={`Dismiss ${doc.name}`}
            />
          ))}
        </div>
      ) : (
        <div className="rounded-lg border border-border bg-muted/30 px-4 py-3">
          <p className="text-sm font-medium">No sources yet</p>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            {savedCount > 0
              ? `That is fine — ${savedCount} question${savedCount === 1 ? "" : "s"} will come from your saved bank. Add a chapter if you also want new questions written.`
              : "Add a chapter so we can write questions from it. Reading, grammar and writing sections do not need one."}
          </p>
        </div>
      )}
    </div>
  );
}
