"use client";

/**
 * Saved paper recipes — "Weekly Test", "Friday recap", "Chapter revision".
 *
 * Schools set the same paper shape over and over, and General Instructions
 * Mode makes each one a fresh typing exercise. A template is that typing kept:
 * the prose AND the settings that were filled in around it, so re-applying one
 * does not re-ask for difficulty or set count.
 *
 * Deliberately small. This is a shortcut next to a text box, not a feature with
 * its own management screen — a dropdown to apply one, and a button to save
 * what is currently typed.
 */

import { useCallback, useEffect, useState } from "react";
import { BookmarkPlus, ChevronDown, Loader2, Trash2 } from "lucide-react";
import { toast } from "sonner";

import {
  applyPaperTemplate,
  deletePaperTemplate,
  fetchPaperTemplates,
  savePaperTemplate,
  type PaperTemplate,
} from "@/lib/api-client";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

export interface TemplatePickerProps {
  /** What "Save as template" captures. */
  instructions: string;
  settings: Record<string, string>;
  /** Applied template: instructions replace the box, settings fill the form. */
  onApply: (template: PaperTemplate) => void;
  className?: string;
}

export function TemplatePicker({
  instructions,
  settings,
  onApply,
  className,
}: TemplatePickerProps) {
  const [templates, setTemplates] = useState<PaperTemplate[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setTemplates(await fetchPaperTemplates());
    } catch {
      // A template list that will not load is not worth a toast on mount —
      // the teacher can still type their instructions.
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleApply = async (template: PaperTemplate) => {
    try {
      // Round-trips so the backend can stamp `last_used_at`, which is what
      // floats a weekly template above one made once and abandoned.
      const fresh = await applyPaperTemplate(template.id);
      onApply(fresh);
      setTemplates((prev) => [
        fresh,
        ...prev.filter((t) => t.id !== fresh.id),
      ]);
      toast.success(`Applied "${fresh.name}".`);
    } catch {
      // The local copy is as good as the server's for applying; only the
      // ordering signal is lost.
      onApply(template);
      toast.success(`Applied "${template.name}".`);
    }
  };

  const handleDelete = async (template: PaperTemplate) => {
    setTemplates((prev) => prev.filter((t) => t.id !== template.id));
    try {
      await deletePaperTemplate(template.id);
    } catch {
      toast.error("Could not delete that template.");
      void load();
    }
  };

  const handleSave = async () => {
    const text = instructions.trim();
    if (!text) {
      toast.error("Write the instructions first, then save them as a template.");
      return;
    }
    const name = window.prompt("Name this template", "Weekly Test")?.trim();
    if (!name) return;

    setSaving(true);
    try {
      const saved = await savePaperTemplate({
        name,
        instructions: text,
        settings,
      });
      setTemplates((prev) => [saved, ...prev.filter((t) => t.id !== saved.id)]);
      toast.success(`Saved "${saved.name}".`);
    } catch (error: unknown) {
      toast.error(
        error instanceof Error ? error.message : "Could not save that template.",
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className={cn("flex items-center gap-1.5", className)}>
      <DropdownMenu>
        <DropdownMenuTrigger
          className="inline-flex h-7 items-center gap-1 rounded-md border border-border px-2 text-[11.5px] text-muted-foreground transition-colors hover:text-foreground disabled:opacity-50"
          disabled={loading && templates.length === 0}
        >
          {loading && templates.length === 0 ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : null}
          Templates
          {templates.length > 0 && (
            <span className="tabular-nums opacity-60">{templates.length}</span>
          )}
          <ChevronDown className="h-3 w-3" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-64">
          {templates.length === 0 ? (
            <div className="px-2 py-3 text-center text-[11.5px] text-muted-foreground">
              No templates yet. Write your instructions, then save them.
            </div>
          ) : (
            templates.map((template) => (
              <DropdownMenuItem
                key={template.id}
                onSelect={(event) => {
                  event.preventDefault();
                  void handleApply(template);
                }}
                className="group flex items-start gap-2"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[12.5px] font-medium">
                    {template.name}
                  </p>
                  <p className="truncate text-[11px] text-muted-foreground">
                    {template.instructions}
                  </p>
                </div>
                <button
                  type="button"
                  aria-label={`Delete ${template.name}`}
                  onClick={(event) => {
                    event.stopPropagation();
                    void handleDelete(template);
                  }}
                  className="shrink-0 rounded p-1 text-muted-foreground opacity-0 hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </DropdownMenuItem>
            ))
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      <button
        type="button"
        onClick={handleSave}
        disabled={saving || !instructions.trim()}
        title="Save these instructions as a reusable template"
        className="inline-flex h-7 items-center gap-1 rounded-md border border-border px-2 text-[11.5px] text-muted-foreground transition-colors hover:text-foreground disabled:opacity-40"
      >
        {saving ? (
          <Loader2 className="h-3 w-3 animate-spin" />
        ) : (
          <BookmarkPlus className="h-3 w-3" />
        )}
        Save
      </button>
    </div>
  );
}
