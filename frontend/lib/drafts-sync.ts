/**
 * The server's copy of a draft, and how it meets the local one.
 *
 * IndexedDB stays the authority for speed — every keystroke lands there, and
 * nothing in this file is on that path. What this adds is a second copy that
 * outlives the browser: a paper started on a laptop can be finished on the
 * staffroom PC, and clearing site data stops being a way to lose a term's
 * work.
 *
 * Three rules, and they are the whole design:
 *
 * 1. **Push is best-effort.** A server that is down, slow, or refusing must
 *    never stop the teacher typing or show them a failure. The local write has
 *    already succeeded by the time we get here; the server copy is insurance,
 *    and insurance that interrupts the work is worse than none.
 * 2. **Last write wins, on the client's clock.** Two devices are ordered by
 *    when the teacher typed, not by whose request arrived first — otherwise a
 *    slow connection lets a stale device overwrite newer work.
 * 3. **Only unsaved work.** A draft that has become a paper has a real backend
 *    row, and that row is authoritative. Pushing it here too would leave two
 *    copies quietly diverging.
 */

import { fetchJson } from "@/lib/api-client";
import { basePaperId, splitPaperId } from "@/lib/paper-id";
import {
  getLiveDocumentId,
  listLiveDocumentsForUser,
  saveLiveDocument,
  type LiveEditorDocument,
} from "@/lib/live-document-db";

/** A draft row as the server returns it. `document` only on the detail path. */
export type ServerDraft = {
  id: string;
  scope: string;
  setLabel: string;
  title: string;
  className: string;
  subject: string;
  clientUpdatedAt: number;
  updated_at: string;
  document?: LiveEditorDocument;
};

type DraftListResponse = {
  retention_days: number;
  drafts: ServerDraft[];
};

/**
 * Split a composed live-document id into what the server stores.
 *
 * Local ids are `"paper:{userId}:{scope}_{SET}"` (or the pre-set-tabs
 * `"current:{userId}"`). The server keys on `(scope, setLabel)` — the base id
 * and the tab — because that is the pair that identifies one editable
 * document across devices, where a userId-prefixed local key does not.
 */
export function splitDocumentId(
  document: Pick<LiveEditorDocument, "id" | "userId">,
): { scope: string; setLabel: string } | null {
  const marker = `paper:${document.userId}:`;
  if (!document.id.startsWith(marker)) {
    return document.id.startsWith("current:")
      ? { scope: "current", setLabel: "" }
      : null;
  }
  const scoped = document.id.slice(marker.length);
  const scope = basePaperId(scoped);
  if (!scope) return null;
  return { scope, setLabel: splitPaperId(scoped).set ?? "" };
}

/** True for a document that is genuinely unsaved work. */
export function isUnsavedDraft(document: LiveEditorDocument): boolean {
  if (document.id.startsWith("archived:")) return false;
  return !document.paperId || document.paperId.startsWith("current");
}

/**
 * Send one draft up. Never throws, never reports — see rule 1.
 *
 * A 409 means another device has newer work; the server hands back the winning
 * row, and the caller reconciles by writing it into IndexedDB. We do not
 * clobber the local copy from here: the teacher may be mid-sentence, and
 * yanking the document out from under them to resolve a conflict they cannot
 * see is worse than one device being briefly behind. The reconciliation
 * happens on the next load, which is when it is safe.
 */
export async function pushDraft(document: LiveEditorDocument): Promise<void> {
  if (!isUnsavedDraft(document)) return;
  const key = splitDocumentId(document);
  if (!key) return;

  try {
    await fetchJson("/api/projects/drafts", {
      method: "PUT",
      body: JSON.stringify({
        scope: key.scope,
        setLabel: key.setLabel,
        document,
        clientUpdatedAt: document.updatedAt,
      }),
      timeoutMs: 15000,
    });
  } catch (error) {
    // Deliberately silent. The local copy is already written; the teacher has
    // nothing to do about a failed server copy, and a toast on every debounce
    // tick over a flaky connection would be its own bug.
    console.debug("Draft server sync skipped:", error);
  }
}

/**
 * Bring IndexedDB up to date with the server, then return every local draft.
 *
 * This is where a draft made on another device becomes visible here. Only
 * strictly-newer server rows are written down, so a local copy that is ahead
 * (the common case — you are on the machine you were working on) is left
 * exactly as it is.
 *
 * Best-effort in the same way `pushDraft` is: if the server cannot be reached,
 * the caller still gets the local drafts, which is what the page showed before
 * any of this existed.
 */
export async function pullDrafts(
  userId: string,
): Promise<{ documents: LiveEditorDocument[]; retentionDays: number | null }> {
  const local = await listLiveDocumentsForUser(userId);

  let response: DraftListResponse;
  try {
    response = await fetchJson<DraftListResponse>("/api/projects/drafts", {
      method: "GET",
      timeoutMs: 15000,
    });
  } catch (error) {
    console.debug("Could not read server drafts:", error);
    return { documents: local, retentionDays: null };
  }

  const localByKey = new Map<string, LiveEditorDocument>();
  for (const document of local) {
    const key = splitDocumentId(document);
    if (key) localByKey.set(`${key.scope}|${key.setLabel}`, document);
  }

  // Only the ones the server is ahead on need their bodies fetching, which is
  // why the list endpoint omits them: on the machine you were just working on,
  // that set is empty and the whole reconciliation costs one small request.
  const stale = response.drafts.filter((remote) => {
    const mine = localByKey.get(`${remote.scope}|${remote.setLabel}`);
    return !mine || remote.clientUpdatedAt > mine.updatedAt;
  });

  const hydrated: LiveEditorDocument[] = [];
  await Promise.all(
    [...new Set(stale.map((d) => d.scope))].map(async (scope) => {
      try {
        const rows = await fetchJson<ServerDraft[]>(
          `/api/projects/drafts/${encodeURIComponent(scope)}`,
          { method: "GET", timeoutMs: 20000 },
        );
        for (const row of rows) {
          const document = row.document;
          if (!document) continue;
          const mine = localByKey.get(`${row.scope}|${row.setLabel}`);
          if (mine && row.clientUpdatedAt <= mine.updatedAt) continue;
          // Re-key to this browser's id space. The server's row is keyed by
          // (scope, set) and carries whichever userId wrote it; the local
          // store is keyed per user, and a foreign id would make the draft
          // unreachable from the editor.
          const localised: LiveEditorDocument = {
            ...document,
            id: getLiveDocumentId(
              userId,
              row.setLabel ? `${row.scope}_${row.setLabel}` : row.scope,
            ),
            userId,
            updatedAt: row.clientUpdatedAt || document.updatedAt,
          };
          await saveLiveDocument(localised);
          hydrated.push(localised);
        }
      } catch (error) {
        console.debug("Could not hydrate server draft:", scope, error);
      }
    }),
  );

  const documents = hydrated.length
    ? await listLiveDocumentsForUser(userId)
    : local;
  return { documents, retentionDays: response.retention_days ?? null };
}

/**
 * Drop the server's copy of a draft.
 *
 * Called both when a teacher deletes a draft and when one is saved as a paper.
 * The second case is the one that matters: from that moment the Paper row is
 * authoritative, and a surviving draft is a second copy that will diverge from
 * it and then reappear in the drafts strip as a ghost of a paper that already
 * exists.
 */
export async function deleteServerDraft(scope: string): Promise<void> {
  if (!scope) return;
  try {
    await fetchJson(`/api/projects/drafts/${encodeURIComponent(scope)}`, {
      method: "DELETE",
      timeoutMs: 15000,
    });
  } catch (error) {
    console.debug("Could not delete server draft:", scope, error);
  }
}
