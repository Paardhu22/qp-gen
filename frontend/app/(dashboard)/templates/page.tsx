"use client";

/**
 * Templates — the management surface for every exam recipe in the account.
 *
 * This replaced `/build-paper`, which was a two-pane bank workspace wearing a
 * "Builder" label and had nothing to do with templates. The capability it
 * carried (assemble a paper from already-saved questions) moved into the
 * editor's generation flow, where it belongs, so nothing was orphaned.
 *
 * Two kinds of template share the list, and the difference is real rather than
 * cosmetic. Built-ins are generated server-side from the engine's eligibility
 * matrix — code, not rows — which is what keeps the catalog in step with the
 * engine for free, and also means a built-in has nothing to edit and nowhere to
 * be filed. "Make it mine" forks one into a row the teacher owns, and from that
 * point it behaves like anything else here.
 *
 * Folders are pure filing: nothing in generation reads them, and an unfiled
 * template is completely usable. See backend `TemplateFolder`.
 */

import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { errorWithRetry } from "@/lib/toasts";
import { LayoutTemplate, Search, X, Plus } from "lucide-react";

import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { PageTitle } from "@/components/ui/page-title";
import { SkeletonCards } from "@/components/ui/skeleton";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  FolderRail,
  type FolderSelection,
} from "@/components/templates/folder-rail";
import {
  BuiltinTemplateCard,
  SavedTemplateCard,
} from "@/components/templates/template-card";
import { TemplateEditorPanel } from "@/components/templates/template-editor-panel";
import {
  createTemplateFolder,
  deletePaperTemplate,
  deleteTemplateFolder,
  duplicatePaperTemplate,
  fetchTemplateCatalog,
  fetchTemplateFolders,
  forkBuiltinTemplate,
  updatePaperTemplate,
  updateTemplateFolder,
  type BuiltinTemplate,
  type PaperTemplate,
  type TemplateFolder,
} from "@/lib/api-client";
import { useEditorStore } from "@/store/editor-store";

/** Mirrors backend MAX_FOLDER_DEPTH. Used only to hide actions the API rejects. */
const MAX_FOLDER_DEPTH = 3;

type PendingDelete =
  | { kind: "template"; id: string; name: string }
  | { kind: "folder"; id: string; name: string; templateCount: number };

export default function TemplatesPage() {
  const router = useRouter();
  const setTemplateHandoff = useEditorStore((s) => s.setTemplateHandoff);

  const [templates, setTemplates] = React.useState<PaperTemplate[]>([]);
  const [builtins, setBuiltins] = React.useState<BuiltinTemplate[]>([]);
  const [folders, setFolders] = React.useState<TemplateFolder[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);

  const [selection, setSelection] = React.useState<FolderSelection>({
    kind: "all",
  });
  const [search, setSearch] = React.useState("");
  const [editing, setEditing] = React.useState<PaperTemplate | null>(null);
  const [forkingId, setForkingId] = React.useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = React.useState<PendingDelete | null>(
    null,
  );
  const [isCreatorOpen, setIsCreatorOpen] = React.useState(false);
  const [creatorFolderId, setCreatorFolderId] = React.useState<string | null>(
    null,
  );

  const load = React.useCallback(async function load() {
    setIsLoading(true);
    try {
      const [catalog, folderRows] = await Promise.all([
        fetchTemplateCatalog(),
        fetchTemplateFolders(),
      ]);
      setTemplates(catalog.templates);
      setBuiltins(catalog.builtin);
      setFolders(folderRows);
    } catch (error: any) {
      errorWithRetry(error?.message || "Could not load your templates.", load);
    } finally {
      setIsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  /** Folder counts live on the folder rows; refresh them after any filing change. */
  const refreshFolders = React.useCallback(async () => {
    try {
      setFolders(await fetchTemplateFolders());
    } catch {
      // The counts going stale is not worth an error toast on top of whatever
      // the user was actually doing; the next load fixes it.
    }
  }, []);

  const counts = React.useMemo(
    () => ({
      all: templates.length,
      unfiled: templates.filter((t) => !t.folderId).length,
      builtin: builtins.length,
    }),
    [templates, builtins],
  );

  const term = search.trim().toLowerCase();

  const visibleTemplates = React.useMemo(() => {
    let rows = templates;
    if (selection.kind === "unfiled") rows = rows.filter((t) => !t.folderId);
    if (selection.kind === "folder") {
      rows = rows.filter((t) => t.folderId === selection.id);
    }
    if (term) {
      rows = rows.filter((t) =>
        [t.name, t.instructions, t.base_template_id]
          .filter(Boolean)
          .join(" ")
          .toLowerCase()
          .includes(term),
      );
    }
    return rows;
  }, [templates, selection, term]);

  const visibleBuiltins = React.useMemo(() => {
    if (!term) return builtins;
    return builtins.filter((t) =>
      [t.name, t.description, t.subject].join(" ").toLowerCase().includes(term),
    );
  }, [builtins, term]);

  /* ── Actions ─────────────────────────────────────────────────────────── */

  const handleUse = (templateId: string, templateName: string) => {
    // The editor owns generation; this page owns choosing. Only the id crosses
    // — the Builder resolves the template server-side, so shipping a copy of
    // its blueprint through the store would be a second source of truth for
    // something that can change between here and there.
    setTemplateHandoff({ id: templateId, name: templateName });
    router.push("/editor");
  };

  const handleFork = async (builtin: BuiltinTemplate) => {
    setForkingId(builtin.id);
    try {
      const created = await forkBuiltinTemplate({
        templateId: builtin.id,
        subject: builtin.subject,
        academicClass: builtin.academicClass,
        folderId: selection.kind === "folder" ? selection.id : null,
      });
      setTemplates((prev) => [created, ...prev]);
      await refreshFolders();
      toast.success(`"${created.name}" is yours now — edit it however you like.`);
      setSelection(
        created.folderId
          ? { kind: "folder", id: created.folderId }
          : { kind: "unfiled" },
      );
    } catch (error: any) {
      toast.error(error?.message || "Could not copy that template.");
    } finally {
      setForkingId(null);
    }
  };

  const handleDuplicate = async (template: PaperTemplate) => {
    try {
      const copy = await duplicatePaperTemplate(template.id);
      setTemplates((prev) => [copy, ...prev]);
      await refreshFolders();
      toast.success(`Duplicated as "${copy.name}"`);
    } catch (error: any) {
      toast.error(error?.message || "Could not duplicate that template.");
    }
  };

  const handleMove = async (
    template: PaperTemplate,
    folderId: string | null,
  ) => {
    try {
      const saved = await updatePaperTemplate(template.id, { folderId });
      setTemplates((prev) =>
        prev.map((t) => (t.id === saved.id ? saved : t)),
      );
      await refreshFolders();
      const target = folderId
        ? folders.find((f) => f.id === folderId)?.name
        : "Unfiled";
      toast.success(`Moved to ${target}`);
    } catch (error: any) {
      toast.error(error?.message || "Could not move that template.");
    }
  };

  const handleCreateFolder = async (name: string, parentId: string | null) => {
    try {
      const folder = await createTemplateFolder({ name, parentId });
      setFolders((prev) => [...prev, folder]);
      setSelection({ kind: "folder", id: folder.id });
    } catch (error: any) {
      toast.error(error?.message || "Could not create that folder.");
    }
  };

  const handleRenameFolder = async (id: string, name: string) => {
    try {
      const folder = await updateTemplateFolder(id, { name });
      setFolders((prev) => prev.map((f) => (f.id === id ? folder : f)));
    } catch (error: any) {
      toast.error(error?.message || "Could not rename that folder.");
    }
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    const target = pendingDelete;
    setPendingDelete(null);

    try {
      if (target.kind === "template") {
        await deletePaperTemplate(target.id);
        setTemplates((prev) => prev.filter((t) => t.id !== target.id));
        await refreshFolders();
        toast.success(`Deleted "${target.name}"`);
        return;
      }

      await deleteTemplateFolder(target.id);
      // Subfolders go with it server-side; the templates inside do not. Mirror
      // both here so the list is right without a reload.
      const removed = new Set<string>([target.id]);
      let grew = true;
      while (grew) {
        grew = false;
        for (const folder of folders) {
          if (folder.parentId && removed.has(folder.parentId) && !removed.has(folder.id)) {
            removed.add(folder.id);
            grew = true;
          }
        }
      }
      setFolders((prev) => prev.filter((f) => !removed.has(f.id)));
      setTemplates((prev) =>
        prev.map((t) =>
          t.folderId && removed.has(t.folderId) ? { ...t, folderId: null } : t,
        ),
      );
      if (selection.kind === "folder" && removed.has(selection.id)) {
        setSelection({ kind: "all" });
      }
      toast.success(
        target.templateCount > 0
          ? `Deleted "${target.name}". Its templates are now unfiled.`
          : `Deleted "${target.name}"`,
      );
    } catch (error: any) {
      toast.error(error?.message || "Could not delete that.");
    }
  };

  /* ── Render ──────────────────────────────────────────────────────────── */

  const showingBuiltins = selection.kind === "builtin";
  const heading =
    selection.kind === "all"
      ? "All templates"
      : selection.kind === "unfiled"
        ? "Unfiled"
        : selection.kind === "builtin"
          ? "Built-in templates"
          : (folders.find((f) => f.id === selection.id)?.name ?? "Folder");

  return (
    <div className="flex min-h-0 flex-1">
      <aside className="hidden w-60 shrink-0 border-r border-border lg:flex lg:flex-col">
        <FolderRail
          folders={folders}
          selection={selection}
          onSelect={setSelection}
          counts={counts}
          onCreateFolder={handleCreateFolder}
          onRenameFolder={handleRenameFolder}
          onDeleteFolder={(id) => {
            const folder = folders.find((f) => f.id === id);
            if (!folder) return;
            setPendingDelete({
              kind: "folder",
              id,
              name: folder.name,
              templateCount: folder.templateCount,
            });
          }}
          onCreateTemplate={(folderId) => {
            setCreatorFolderId(folderId === "unfiled" ? null : folderId);
            setIsCreatorOpen(true);
          }}
          maxDepth={MAX_FOLDER_DEPTH}
        />
      </aside>

      <main className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div className="flex shrink-0 flex-wrap items-center gap-3 border-b border-border px-4 py-3 sm:px-6">
          <div className="flex items-center gap-2">
            <LayoutTemplate className="h-4 w-4 text-primary" />
            <PageTitle>{heading}</PageTitle>
          </div>

          <Button 
            variant="outline" 
            size="sm" 
            className="ml-2 gap-2 hidden sm:flex"
            onClick={() => {
              setCreatorFolderId(
                selection.kind === "folder" ? selection.id : null,
              );
              setIsCreatorOpen(true);
            }}
          >
            <Plus className="h-4 w-4" />
            New Template
          </Button>

          <div className="relative ml-auto w-full max-w-xs">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search templates"
              className="h-8 pl-8 pr-8 text-sm"
            />
            {search ? (
              <button
                type="button"
                onClick={() => setSearch("")}
                aria-label="Clear search"
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            ) : null}
          </div>
        </div>

        {/* The folder rail is desktop-only; on a phone the same buckets have to
            be reachable, so they collapse into a scrolling chip row. */}
        <div className="flex shrink-0 gap-2 overflow-x-auto border-b border-border px-4 py-2 lg:hidden">
          {(
            [
              { key: "all", label: `All (${counts.all})`, sel: { kind: "all" } },
              {
                key: "unfiled",
                label: `Unfiled (${counts.unfiled})`,
                sel: { kind: "unfiled" },
              },
              {
                key: "builtin",
                label: `Built-in (${counts.builtin})`,
                sel: { kind: "builtin" },
              },
              ...folders.map((f) => ({
                key: `folder:${f.id}`,
                label: `${f.name} (${f.templateCount})`,
                sel: { kind: "folder" as const, id: f.id },
              })),
            ] as { key: string; label: string; sel: FolderSelection }[]
          ).map((chip) => (
            <button
              key={chip.key}
              type="button"
              onClick={() => setSelection(chip.sel)}
              className={
                selectionMatches(selection, chip.sel)
                  ? "shrink-0 rounded-full bg-primary px-3 py-1 text-xs font-medium text-primary-foreground"
                  : "shrink-0 rounded-full bg-muted px-3 py-1 text-xs text-muted-foreground"
              }
            >
              {chip.label}
            </button>
          ))}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-6">
          {isLoading ? (
            <SkeletonCards cards={6} className="xl:grid-cols-3" />
          ) : showingBuiltins ? (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {visibleBuiltins.map((builtin) => (
                <BuiltinTemplateCard
                  key={builtin.id}
                  template={builtin}
                  isForking={forkingId === builtin.id}
                  onFork={() => void handleFork(builtin)}
                  onUse={() => handleUse(builtin.id, builtin.name)}
                />
              ))}
            </div>
          ) : visibleTemplates.length === 0 ? (
            <EmptyState
              searching={Boolean(term)}
              onBrowseBuiltins={() => setSelection({ kind: "builtin" })}
            />
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {visibleTemplates.map((template) => (
                <SavedTemplateCard
                  key={template.id}
                  template={template}
                  folders={folders}
                  onEdit={() => setEditing(template)}
                  onUse={() => handleUse(template.id, template.name)}
                  onDuplicate={() => void handleDuplicate(template)}
                  onMove={(folderId) => void handleMove(template, folderId)}
                  onDelete={() =>
                    setPendingDelete({
                      kind: "template",
                      id: template.id,
                      name: template.name,
                    })
                  }
                />
              ))}
            </div>
          )}
        </div>
      </main>

      {editing ? (
        <TemplateEditorPanel
          template={editing}
          folders={folders}
          onClose={() => setEditing(null)}
          onSaved={(saved) => {
            setTemplates((prev) =>
              prev.map((t) => (t.id === saved.id ? saved : t)),
            );
            setEditing(null);
            void refreshFolders();
          }}
        />
      ) : null}

      <AlertDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              Delete &ldquo;{pendingDelete?.name}&rdquo;?
            </AlertDialogTitle>
            <AlertDialogDescription>
              {pendingDelete?.kind === "folder"
                ? pendingDelete.templateCount > 0
                  ? `Its ${pendingDelete.templateCount} template${
                      pendingDelete.templateCount === 1 ? "" : "s"
                    } will not be deleted — they move back to Unfiled. Any subfolders are removed.`
                  : "Any subfolders are removed. Templates inside would move back to Unfiled."
                : "This cannot be undone. Papers you already generated from it are unaffected."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => void confirmDelete()}>
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {isCreatorOpen ? (
        <TemplateEditorPanel
          template={null}
          folders={folders}
          initialFolderId={creatorFolderId}
          onClose={() => setIsCreatorOpen(false)}
          onSaved={(created) => {
            setTemplates((prev) => [created, ...prev]);
            setIsCreatorOpen(false);
            void refreshFolders();
          }}
        />
      ) : null}
    </div>
  );
}

function selectionMatches(a: FolderSelection, b: FolderSelection): boolean {
  if (a.kind !== b.kind) return false;
  if (a.kind === "folder" && b.kind === "folder") return a.id === b.id;
  return true;
}

function EmptyState({
  searching,
  onBrowseBuiltins,
}: {
  searching: boolean;
  onBrowseBuiltins: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-24 text-center">
      <LayoutTemplate className="empty-breathe h-10 w-10 opacity-30" />
      <p className="text-sm font-medium">
        {searching ? "No templates match that." : "Nothing here yet."}
      </p>
      {!searching ? (
        <>
          <p className="max-w-sm text-xs leading-relaxed text-muted-foreground">
            Start from a built-in CBSE paper under &quot;Built-in&quot; and make
            it yours, or save a template the next time you generate one.
          </p>
          {/* Switches the rail selection in place rather than navigating --
              the built-ins are a view of this same page. */}
          <button
            type="button"
            onClick={onBrowseBuiltins}
            className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground transition-colors hover:bg-primary/90"
          >
            <LayoutTemplate className="h-3.5 w-3.5" />
            Browse built-in templates
          </button>
        </>
      ) : null}
    </div>
  );
}
