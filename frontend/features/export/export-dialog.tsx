"use client";

import { useEffect, useRef, useState } from "react";
import { Download, FileText, FileType } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

import { useExportDialog } from "./export-dialog-store";
import { sanitizeFilename, stemOf } from "./filename";
import type { FileFormat } from "./s3-upload";

const FORMATS: {
  value: FileFormat;
  label: string;
  hint: string;
  Icon: typeof FileText;
}[] = [
  { value: "pdf", label: "PDF", hint: "Print-ready, looks the same everywhere", Icon: FileText },
  { value: "docx", label: "Word", hint: "Editable in Microsoft Word", Icon: FileType },
];

interface ExportDialogProps {
  /** Suggested filename without extension; re-read each time the dialog opens. */
  defaultName: string;
  /** Called with the chosen format and a finished filename (extension included). */
  onExport: (format: FileFormat, filename: string) => void;
  /** Disables the confirm button while the paper is still loading. */
  disabled?: boolean;
}

export function ExportDialog({ defaultName, onExport, disabled }: ExportDialogProps) {
  const { open, format, setOpen, show } = useExportDialog();
  const [name, setName] = useState(defaultName);
  const inputRef = useRef<HTMLInputElement>(null);

  // A fresh suggestion every time the dialog opens, so a changed title or set
  // is reflected without discarding what was typed mid-session.
  useEffect(() => {
    if (open) setName(defaultName);
  }, [open]);

  const clean = sanitizeFilename(stemOf(name));
  const canExport = !disabled && clean.length > 0;

  const confirm = () => {
    if (!canExport) return;
    setOpen(false);
    onExport(format, `${clean}.${format}`);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Export paper</DialogTitle>
          <DialogDescription>
            Download this paper exactly as it appears in the editor.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4">
          <div role="radiogroup" aria-label="File format" className="grid grid-cols-2 gap-2">
            {FORMATS.map(({ value, label, hint, Icon }) => {
              const active = value === format;
              return (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  onClick={() => show(value)}
                  className={cn(
                    "flex flex-col items-start gap-1.5 rounded-xl border p-3 text-left transition-colors",
                    "focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/20",
                    active
                      ? "border-primary bg-primary/5 ring-1 ring-primary/30"
                      : "border-border hover:bg-accent",
                  )}
                >
                  <Icon className={cn("h-5 w-5", active ? "text-primary" : "text-muted-foreground")} />
                  <span className="text-sm font-medium text-foreground">{label}</span>
                  <span className="text-xs leading-snug text-muted-foreground">{hint}</span>
                </button>
              );
            })}
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor="export-filename">File name</Label>
            <div className="relative">
              <Input
                id="export-filename"
                ref={inputRef}
                value={name}
                autoFocus
                onFocus={(e) => e.currentTarget.select()}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    confirm();
                  }
                }}
                className="pr-14"
                maxLength={120}
              />
              <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-xs text-muted-foreground">
                .{format}
              </span>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button onClick={confirm} disabled={!canExport}>
            <Download className="mr-1.5 h-4 w-4" />
            Download {format === "pdf" ? "PDF" : "Word"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
