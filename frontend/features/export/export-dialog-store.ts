import { create } from "zustand";
import type { FileFormat } from "./s3-upload";

/**
 * Whether the export dialog is open, and which format it opens on.
 *
 * Deliberately not part of `editor-store`: that store is persisted, and a
 * dialog that reopens itself after a reload is a bug, not a feature. The
 * toolbar buttons, the Papers-page links (`?action=export-pdf`) and the
 * dialog itself all need to reach it, hence a store rather than props.
 */
interface ExportDialogState {
  open: boolean;
  format: FileFormat;
  show: (format?: FileFormat) => void;
  setOpen: (open: boolean) => void;
}

export const useExportDialog = create<ExportDialogState>((set) => ({
  open: false,
  format: "pdf",
  show: (format) =>
    set((s) => ({ open: true, format: format ?? s.format })),
  setOpen: (open) => set({ open }),
}));
