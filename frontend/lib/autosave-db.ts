export interface AutosaveDraft {
  id: string; // "current_draft" or paperId
  paperId: string | null;
  title: string;
  template: string;
  editorJSON: any;
  structuredData: {
    metadata: {
      title: string;
      template: string;
      updatedAt: number;
    };
    sections: any[];
    questions: any[];
  };
  updatedAt: number;
}

const DB_NAME = "qp_gen_editor_db";
const STORE_NAME = "drafts";
const DB_VERSION = 1;

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
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: "id" });
      }
    };
  });
}

export async function saveDraft(draft: AutosaveDraft): Promise<void> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORE_NAME, "readwrite");
    const store = transaction.objectStore(STORE_NAME);
    const request = store.put(draft);

    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve();
  });
}

export async function getDraft(id: string = "current_draft"): Promise<AutosaveDraft | null> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORE_NAME, "readonly");
    const store = transaction.objectStore(STORE_NAME);
    const request = store.get(id);

    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result || null);
  });
}

export async function clearDraft(id: string = "current_draft"): Promise<void> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORE_NAME, "readwrite");
    const store = transaction.objectStore(STORE_NAME);
    const request = store.delete(id);

    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve();
  });
}
