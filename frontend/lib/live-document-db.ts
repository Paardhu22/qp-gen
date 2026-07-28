import { isExpiredDraft } from "@/lib/drafts";

export type LiveSyncStatus = "pending" | "synced" | "failed";

export interface LiveEditorDocument {
  id: string;
  userId: string;
  paperId: string | null;
  title: string;
  template: string;
  editorJSON: any;
  pages: Array<{ id: string; blocks: any[] }>;
  metadata: {
    title: string;
    className: string;
    subject: string;
    template: string;
    updatedAt: number;
    hsatSources?: any[];
    uploadedDocs?: any[];
  };
  layout: {
    pageSize: "A4";
    orientation: "portrait";
    template: string;
    pages: Array<{ id: string; blocks: any[] }>;
  };
  sync: {
    status: LiveSyncStatus;
    lastSyncedAt: number | null;
    error?: string | null;
  };
  updatedAt: number;
  /**
   * ID of the browser session that last wrote this document. The editor
   * page seeds this from sessionStorage on mount; the resume modal
   * suppresses itself when the latest doc carries the current session's
   * id (i.e. the user is simply navigating within the same session).
   */
  sessionId?: string;
}

const DB_NAME = "qp_gen_editor_db";
const STORE_NAME = "live_documents";
const DB_VERSION = 2;

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("IndexedDB is not supported in this environment"));
      return;
    }

    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result);

    request.onupgradeneeded = () => {
      const db = request.result;
      if (db.objectStoreNames.contains("drafts")) {
        db.deleteObjectStore("drafts");
      }
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        const store = db.createObjectStore(STORE_NAME, { keyPath: "id" });
        store.createIndex("userId", "userId", { unique: false });
        store.createIndex("updatedAt", "updatedAt", { unique: false });
      }
    };
  });
}

export function getLiveDocumentId(
  userId: string,
  paperId?: string | null,
): string {
  return paperId && paperId !== "current"
    ? `paper:${userId}:${paperId}`
    : `current:${userId}`;
}

export async function saveLiveDocument(
  document: LiveEditorDocument,
): Promise<void> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORE_NAME, "readwrite");
    const store = transaction.objectStore(STORE_NAME);
    const request = store.put(document);

    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve();
  });
}

export async function getLiveDocument(
  id: string,
): Promise<LiveEditorDocument | null> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORE_NAME, "readonly");
    const store = transaction.objectStore(STORE_NAME);
    const request = store.get(id);

    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result || null);
  });
}

export async function getLatestLiveDocumentForUser(
  userId: string,
): Promise<LiveEditorDocument | null> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORE_NAME, "readonly");
    const store = transaction.objectStore(STORE_NAME);
    const request = store.getAll();

    request.onerror = () => reject(request.error);
    request.onsuccess = () => {
      const documents = (request.result || []) as LiveEditorDocument[];
      // Exclude archived drafts — the "Create New Paper" action moves the
      // previous draft to an `archived:...` id so it's not destroyed but
      // also doesn't pop the resume modal back up on the next mount.
      const latest = documents
        .filter(
          (document) =>
            document.userId === userId && !document.id.startsWith("archived:"),
        )
        .sort((a, b) => b.updatedAt - a.updatedAt)[0];

      resolve(latest || null);
    };
  });
}

/** Every live document belonging to a user, newest first. Excludes nothing —
 *  callers decide what counts as a draft. */
export async function listLiveDocumentsForUser(
  userId: string,
): Promise<LiveEditorDocument[]> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORE_NAME, "readonly");
    const store = transaction.objectStore(STORE_NAME);
    const request = store.getAll();

    request.onerror = () => reject(request.error);
    request.onsuccess = () => {
      const documents = (request.result || []) as LiveEditorDocument[];
      resolve(
        documents
          .filter((document) => document.userId === userId)
          .sort((a, b) => b.updatedAt - a.updatedAt),
      );
    };
  });
}

/**
 * Delete unsaved drafts last touched more than `DRAFT_RETENTION_DAYS` ago.
 *
 * What counts as expired is `isExpiredDraft` in `lib/drafts.ts` — kept there so
 * the policy is unit-testable without an IndexedDB, and so this file stays a
 * store rather than a place that decides what to throw away.
 *
 * Returns the number of documents deleted. Best-effort: individual failures are
 * logged, never thrown, so a purge can't block the page that triggered it.
 */
export async function purgeExpiredDrafts(
  userId: string,
  now: number = Date.now(),
): Promise<number> {
  let documents: LiveEditorDocument[];
  try {
    documents = await listLiveDocumentsForUser(userId);
  } catch (error) {
    console.error("Failed to read drafts for purge:", error);
    return 0;
  }

  const expired = documents.filter((document) => isExpiredDraft(document, now));

  let deleted = 0;
  await Promise.all(
    expired.map(async (document) => {
      try {
        await deleteLiveDocument(document.id);
        deleted += 1;
      } catch (error) {
        console.error("Failed to purge expired draft:", document.id, error);
      }
    }),
  );
  return deleted;
}

export async function deleteLiveDocument(id: string): Promise<void> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORE_NAME, "readwrite");
    const store = transaction.objectStore(STORE_NAME);
    const request = store.delete(id);

    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve();
  });
}

/**
 * Delete every live draft belonging to one paper: the legacy un-suffixed key
 * plus the per-set `_A`/`_B`/`_C` keys the editor writes for its set tabs.
 * Deleting only the base id leaves orphaned set drafts that the load effect
 * happily re-hydrates, which looks to the user like a deleted paper coming
 * back from the dead. Best-effort — a failed delete never rejects.
 */
export async function deleteLiveDocumentsForPaper(
  userId: string,
  paperId: string | null | undefined,
): Promise<void> {
  const scope = paperId || "current";
  const ids = [scope, `${scope}_A`, `${scope}_B`, `${scope}_C`];
  await Promise.all(
    ids.map((id) =>
      deleteLiveDocument(getLiveDocumentId(userId, id)).catch((err) =>
        console.error("Failed to delete live draft:", id, err),
      ),
    ),
  );
}

export async function clearLiveDocumentsForUser(userId: string): Promise<void> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORE_NAME, "readwrite");
    const store = transaction.objectStore(STORE_NAME);
    const request = store.getAll();

    request.onerror = () => reject(request.error);
    request.onsuccess = () => {
      const documents = (request.result || []) as LiveEditorDocument[];
      const userDocs = documents.filter((doc) => doc.userId === userId);
      const deletePromises = userDocs.map(
        (doc) =>
          new Promise<void>((res, rej) => {
            const req = store.delete(doc.id);
            req.onerror = () => rej(req.error);
            req.onsuccess = () => res();
          }),
      );
      Promise.all(deletePromises).then(() => resolve()).catch(reject);
    };
  });
}
