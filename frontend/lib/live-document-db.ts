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
  return paperId ? `paper:${userId}:${paperId}` : `current:${userId}`;
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
      const latest = documents
        .filter((document) => document.userId === userId)
        .sort((a, b) => b.updatedAt - a.updatedAt)[0];

      resolve(latest || null);
    };
  });
}
