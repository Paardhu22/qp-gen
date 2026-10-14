/** Server-sent-event streaming with resume: the transport under generation and chat streams. */
"use client";

import { getAccessToken } from "@/lib/api/token-storage";
import { ensureFreshTokens, refreshAccessToken } from "@/features/auth/auth-client";
import { API_BASE_URL } from "@/lib/api/api-base-url";
import { ApiError, errorMessageFrom } from "@/lib/api/http";

export type SseEventHandler = (event: string, data: any) => void;

/**
 * Where a generation had got to when the connection dropped.
 *
 * `runId` is the recorded run on the server; `cursor` is how many of its
 * frames this client has already seen. Together they are enough to pick the
 * generation back up without losing or repeating anything — see
 * services/generation_runs.py.
 */
export type SseRunPosition = { runId: string; cursor: number };

export type StreamSseOptions = {
  /** Told the run id and cursor as they advance, so a caller can persist them
   *  and offer to resume after a page reload. */
  onRunPosition?: (position: SseRunPosition) => void;
  /** How many times to re-attach after the transport drops. */
  maxResumes?: number;
};

/** Attempts to re-attach after a dropped connection, before giving up. */
export const DEFAULT_MAX_RESUMES = 3;

/**
 * Read one SSE response, dispatching frames and tracking where we got to.
 *
 * The cursor is counted rather than read off the wire: the server's `follow`
 * emits its stored frames in sequence order, one per recorded event, preceded
 * by a single synthetic `run` frame. So "frames seen since the start cursor,
 * not counting `run`" is exactly the server's sequence number. Keeping the
 * count here means the frames themselves stay byte-identical to what the
 * pipeline produced.
 */
export async function consumeSse(
  response: Response,
  onEvent: SseEventHandler,
  position: { runId: string | null; cursor: number },
  onRunPosition?: (position: SseRunPosition) => void,
): Promise<boolean> {
  if (!response.body) {
    throw new ApiError(
      "The server accepted the request but returned no stream. Check that no " +
        "proxy is buffering text/event-stream responses.",
      response.status,
    );
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let sawTerminalEvent = false;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";

    for (const part of parts) {
      const lines = part.split("\n");
      let event = "message";
      let data = "";

      for (const line of lines) {
        // Lines beginning with ":" are SSE comments. The backend sends them
        // as keepalive pings during long silent stages; they carry no data
        // and must be skipped, not parsed.
        if (line.startsWith(":")) continue;
        if (line.startsWith("event:")) {
          event = line.replace("event:", "").trim();
        } else if (line.startsWith("data:")) {
          data += line.replace("data:", "").trim();
        }
      }

      if (!data) continue;

      if (event === "run") {
        // Synthetic, from the follower. It names the run and is not itself a
        // recorded frame, so it does not advance the cursor.
        try {
          const parsed = JSON.parse(data);
          if (parsed?.runId) {
            position.runId = String(parsed.runId);
            onRunPosition?.({ runId: position.runId, cursor: position.cursor });
          }
        } catch {
          // A malformed run frame costs the ability to resume, nothing else.
        }
        continue;
      }

      position.cursor += 1;
      if (position.runId) {
        onRunPosition?.({ runId: position.runId, cursor: position.cursor });
      }

      if (event === "done" || event === "error") sawTerminalEvent = true;

      // Parse and dispatch are separated on purpose. One `try` used to wrap
      // both, which meant a *handler* that threw was reported to the teacher
      // as a parse failure — and the dashboard's handler threw deliberately,
      // as its way of aborting the stream on an `error` event. So every
      // backend generation error on the chat path ("No usable content in
      // those chapters") arrived as "Failed to parse stream payload", and the
      // real reason was destroyed one frame after it was received.
      //
      // Now a malformed frame is still reported as one, and a throwing
      // handler propagates with its own message, which is what a handler that
      // throws is asking for.
      let payload: unknown;
      try {
        payload = JSON.parse(data);
      } catch {
        onEvent("error", { error: "Failed to parse stream payload" });
        continue;
      }
      onEvent(event, payload);
    }
  }

  return sawTerminalEvent;
}

export async function streamSse(
  path: string,
  payload: Record<string, any>,
  onEvent: SseEventHandler,
  options: StreamSseOptions = {},
): Promise<void> {
  const buildHeaders = () => {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    const accessToken = getAccessToken();
    if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
    return headers;
  };

  // A generation runs for minutes; the token is only checked when the stream
  // connects, so renewing here is what keeps a long paper from dying at the
  // door. Retrying a 401 after the fact would restart the whole generation.
  await ensureFreshTokens();

  let response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: buildHeaders(),
    body: JSON.stringify(payload),
  });
  if (response.status === 401) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      response = await fetch(`${API_BASE_URL}${path}`, {
        method: "POST",
        headers: buildHeaders(),
        body: JSON.stringify(payload),
      });
    }
  }

  if (!response.ok) {
    // A rejected stream is almost always a serializer complaint naming the
    // exact field that is missing or wrong. Report that, not "it failed".
    throw new ApiError(
      await errorMessageFrom(response, "Stream request failed"),
      response.status,
    );
  }

  if (!response.body) {
    // 2xx with no readable body: not a server rejection, so there is no error
    // payload to quote. Distinguish it — it means the transport dropped the
    // stream, not that the request was invalid.
    throw new ApiError(
      "The server accepted the request but returned no stream. Check that no " +
        "proxy is buffering text/event-stream responses.",
      response.status,
    );
  }

  // A generation is only complete when the backend says so. Anything that
  // cuts the connection first — a proxy read timeout, a killed gunicorn
  // worker, a dropped network — surfaces as a clean `done: true` from
  // `reader.read()`, which used to make this function resolve as if the
  // generation had succeeded. The caller then saw no error and no result.
  //
  // Now it means something better: the run is still being produced on the
  // server, and we can go back for the rest of it.
  const position = { runId: null as string | null, cursor: 0 };
  let sawTerminalEvent = await consumeSse(
    response,
    onEvent,
    position,
    options.onRunPosition,
  );

  const maxResumes = options.maxResumes ?? DEFAULT_MAX_RESUMES;
  for (let attempt = 0; !sawTerminalEvent && position.runId && attempt < maxResumes; attempt++) {
    // A short, growing pause. The drop is usually a proxy timing out on a
    // silent stretch, so reconnecting instantly just repeats it.
    await new Promise((resolve) => setTimeout(resolve, 1000 * (attempt + 1)));
    try {
      sawTerminalEvent = await consumeSse(
        await openRunStream(position.runId, position.cursor),
        onEvent,
        position,
        options.onRunPosition,
      );
    } catch {
      // Keep trying until the attempts run out; the error below is the one
      // the caller should see.
      break;
    }
  }

  if (!sawTerminalEvent) {
    throw new ApiError(
      position.runId
        ? "The connection to this generation keeps dropping. It is still " +
          "running on the server — reopen it from your recent generations " +
          "once your connection settles."
        : "The connection closed before generation finished. This usually means " +
          "the request took longer than the server allows — try again, or " +
          "generate fewer chapters at once.",
      response.status,
    );
  }
}

/** Open (or re-open) the event stream of a recorded run at `cursor`. */
export async function openRunStream(runId: string, cursor: number): Promise<Response> {
  await ensureFreshTokens();
  const headers: Record<string, string> = {};
  const accessToken = getAccessToken();
  if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;

  const response = await fetch(
    `${API_BASE_URL}/api/generation/runs/${encodeURIComponent(runId)}/events?cursor=${cursor}`,
    { method: "GET", headers },
  );
  if (!response.ok) {
    throw new ApiError(
      await errorMessageFrom(response, "Could not reopen that generation"),
      response.status,
    );
  }
  return response;
}
