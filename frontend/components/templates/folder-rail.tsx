"use client";

/**
 * The filing rail beside the template list.
 *
 * Three fixed entries sit above the teacher's own folders, and the order is
 * deliberate: **All** first because it is the honest default (a teacher looking
 * for a template does not necessarily remember filing it), **Unfiled** second
 * because it is where everything starts and most things stay, and **Built-in**
 * last because it is a catalog to shop from rather than somewhere you keep
 * things.
 *
 * Folders nest up to the depth the API allows (`MAX_FOLDER_DEPTH`), rendered by
 * walking the flat list into a tree here rather than asking the server for one.
 * A tree endpoint would have to pick a shape; a flat list with `parentId` lets
 * the rail decide, and the server stays the authority on what is legal.
 */

import * as React from "react";
import {
  Folder,
  FolderPlus,
  Inbox,
  Layers,
  MoreHorizontal,
  Pencil,
  Library,
  Trash2,
  FilePlus,
} from "lucide-react";

import { Input } from "@/components/ui/input";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import type { TemplateFolder } from "@/lib/api-client";

/** Which bucket the list is showing. A folder id, or one of the fixed views. */
export type FolderSelection =
  | { kind: "all" }
  | { kind: "unfiled" }
  | { kind: "builtin" }
  | { kind: "folder"; id: string };

export function selectionKey(selection: FolderSelection): string {
  return selection.kind === "folder"
    ? `folder:${selection.id}`
    : selection.kind;
}

interface Props {
  folders: TemplateFolder[];
  selection: FolderSelection;
  onSelect: (selection: FolderSelection) => void;
  /** Counts for the fixed views, computed by the page from the loaded list. */
  counts: { all: number; unfiled: number; builtin: number };
  onCreateFolder: (name: string, parentId: string | null) => Promise<void>;
  onRenameFolder: (id: string, name: string) => Promise<void>;
  onDeleteFolder: (id: string) => void;
  onCreateTemplate: (folderId: string) => void;
  /** Max nesting the API accepts. Deeper folders offer no "add subfolder". */
  maxDepth: number;
}

interface FolderNode extends TemplateFolder {
  children: FolderNode[];
  depth: number;
}

/**
 * Flat rows → tree. Orphans (a `parentId` whose folder is not in the list) are
 * promoted to the root rather than dropped: a folder the teacher can see in no
 * view at all is worse than one filed in the wrong place, and it gives them
 * something to click to fix it.
 */
function toTree(folders: TemplateFolder[]): FolderNode[] {
  const byId = new Map<string, FolderNode>();
  for (const folder of folders) {
    byId.set(folder.id, { ...folder, children: [], depth: 0 });
  }

  const roots: FolderNode[] = [];
  for (const node of byId.values()) {
    const parent = node.parentId ? byId.get(node.parentId) : undefined;
    if (parent) parent.children.push(node);
    else roots.push(node);
  }

  const assignDepth = (nodes: FolderNode[], depth: number) => {
    for (const node of nodes) {
      node.depth = depth;
      node.children.sort((a, b) => a.name.localeCompare(b.name));
      assignDepth(node.children, depth + 1);
    }
  };
  roots.sort((a, b) => a.name.localeCompare(b.name));
  assignDepth(roots, 0);
  return roots;
}

function FixedEntry({
  icon: Icon,
  label,
  count,
  active,
  onClick,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm transition-colors",
        active
          ? "bg-primary/10 font-medium text-primary"
          : "text-foreground hover:bg-accent",
      )}
    >
      <Icon className="h-4 w-4 shrink-0 opacity-70" />
      <span className="flex-1 truncate">{label}</span>
      <span className="text-xs tabular-nums text-muted-foreground">{count}</span>
    </button>
  );
}

function FolderRow({
  node,
  selection,
  onSelect,
  onRename,
  onDelete,
  onAddChild,
  onCreateTemplate,
  maxDepth,
}: {
  node: FolderNode;
  selection: FolderSelection;
  onSelect: (selection: FolderSelection) => void;
  onRename: (id: string, name: string) => Promise<void>;
  onDelete: (id: string) => void;
  onAddChild: (parentId: string) => void;
  onCreateTemplate: (folderId: string) => void;
  maxDepth: number;
}) {
  const [renaming, setRenaming] = React.useState(false);
  const [draft, setDraft] = React.useState(node.name);
  const active = selection.kind === "folder" && selection.id === node.id;
  // The API rejects a folder at maxDepth; hiding the action is kinder than
  // offering it and answering with an error.
  const canNest = node.depth + 1 < maxDepth;

  const commitRename = async () => {
    const name = draft.trim();
    setRenaming(false);
    if (!name || name === node.name) {
      setDraft(node.name);
      return;
    }
    await onRename(node.id, name);
  };

  if (renaming) {
    return (
      <div
        className="px-2 py-1"
        style={{ paddingLeft: `${0.5 + node.depth * 0.75}rem` }}
      >
        <Input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commitRename}
          onKeyDown={(e) => {
            if (e.key === "Enter") void commitRename();
            if (e.key === "Escape") {
              setDraft(node.name);
              setRenaming(false);
            }
          }}
          className="h-7 text-sm"
        />
      </div>
    );
  }

  return (
    <>
      <div
        className={cn(
          "group flex items-center gap-1 rounded-lg pr-1 transition-colors",
          active ? "bg-primary/10" : "hover:bg-accent",
        )}
        style={{ paddingLeft: `${node.depth * 0.75}rem` }}
      >
        <button
          type="button"
          onClick={() => onSelect({ kind: "folder", id: node.id })}
          className={cn(
            "flex min-w-0 flex-1 items-center gap-2 px-2 py-1.5 text-left text-sm",
            active ? "font-medium text-primary" : "text-foreground",
          )}
        >
          <Folder className="h-4 w-4 shrink-0 opacity-70" />
          <span className="flex-1 truncate">{node.name}</span>
          <span className="text-xs tabular-nums text-muted-foreground">
            {node.templateCount}
          </span>
        </button>

        <DropdownMenu>
          <DropdownMenuTrigger
            aria-label={`Actions for ${node.name}`}
            className="rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-background focus-visible:opacity-100 group-hover:opacity-100"
          >
            <MoreHorizontal className="h-3.5 w-3.5" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem
              onClick={() => {
                setDraft(node.name);
                setRenaming(true);
              }}
            >
              <Pencil className="mr-2 h-3.5 w-3.5" />
              Rename
            </DropdownMenuItem>
            {canNest ? (
              <DropdownMenuItem onClick={() => onAddChild(node.id)}>
                <FolderPlus className="mr-2 h-3.5 w-3.5" />
                New subfolder
              </DropdownMenuItem>
            ) : null}
            <DropdownMenuItem onClick={() => onCreateTemplate(node.id)}>
              <FilePlus className="mr-2 h-3.5 w-3.5" />
              New template
            </DropdownMenuItem>
            <DropdownMenuItem
              variant="destructive"
              onClick={() => onDelete(node.id)}
            >
              <Trash2 className="mr-2 h-3.5 w-3.5" />
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {node.children.map((child) => (
        <FolderRow
          key={child.id}
          node={child}
          selection={selection}
          onSelect={onSelect}
          onRename={onRename}
          onDelete={onDelete}
          onAddChild={onAddChild}
          onCreateTemplate={onCreateTemplate}
          maxDepth={maxDepth}
        />
      ))}
    </>
  );
}

export function FolderRail({
  folders,
  selection,
  onSelect,
  counts,
  onCreateFolder,
  onRenameFolder,
  onDeleteFolder,
  onCreateTemplate,
  maxDepth,
}: Props) {
  const tree = React.useMemo(() => toTree(folders), [folders]);
  // Non-null while a new folder is being named. `parentId` null = root.
  const [creating, setCreating] = React.useState<{
    parentId: string | null;
  } | null>(null);
  const [draft, setDraft] = React.useState("");

  const commitCreate = async () => {
    const name = draft.trim();
    const parentId = creating?.parentId ?? null;
    setCreating(null);
    setDraft("");
    if (!name) return;
    await onCreateFolder(name, parentId);
  };

  return (
    <nav className="flex h-full min-h-0 w-full flex-col gap-1 overflow-y-auto p-2">
      <FixedEntry
        icon={Layers}
        label="All templates"
        count={counts.all}
        active={selection.kind === "all"}
        onClick={() => onSelect({ kind: "all" })}
      />
      <FixedEntry
        icon={Inbox}
        label="Unfiled"
        count={counts.unfiled}
        active={selection.kind === "unfiled"}
        onClick={() => onSelect({ kind: "unfiled" })}
      />
      <FixedEntry
        icon={Library}
        label="Built-in"
        count={counts.builtin}
        active={selection.kind === "builtin"}
        onClick={() => onSelect({ kind: "builtin" })}
      />

      <div className="mt-3 flex items-center justify-between px-2">
        <span className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted-foreground">
          Folders
        </span>
        <button
          type="button"
          onClick={() => {
            setDraft("");
            setCreating({ parentId: null });
          }}
          aria-label="New folder"
          className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
        >
          <FolderPlus className="h-3.5 w-3.5" />
        </button>
      </div>

      {tree.length === 0 && !creating ? (
        <p className="px-2 py-3 text-xs leading-relaxed text-muted-foreground">
          No folders yet. Templates work fine unfiled — make a folder when the
          list gets long enough to need one.
        </p>
      ) : null}

      {tree.map((node) => (
        <FolderRow
          key={node.id}
          node={node}
          selection={selection}
          onSelect={onSelect}
          onRename={onRenameFolder}
          onDelete={onDeleteFolder}
          onAddChild={(parentId) => {
            setDraft("");
            setCreating({ parentId });
          }}
          onCreateTemplate={onCreateTemplate}
          maxDepth={maxDepth}
        />
      ))}

      {creating ? (
        <div className="px-2 py-1">
          <Input
            autoFocus
            placeholder="Folder name"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commitCreate}
            onKeyDown={(e) => {
              if (e.key === "Enter") void commitCreate();
              if (e.key === "Escape") {
                setCreating(null);
                setDraft("");
              }
            }}
            className="h-7 text-sm"
          />
        </div>
      ) : null}

      <div className="flex-1" />
    </nav>
  );
}
