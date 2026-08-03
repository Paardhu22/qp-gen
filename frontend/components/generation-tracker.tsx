"use client";

/**
 * The run, visible from anywhere in the app.
 *
 * A generation takes minutes, and a teacher is not going to sit and watch it —
 * they check the question bank, look something up on the dashboard, come back.
 * Before this, leaving the editor meant losing every signal that a paper was
 * being written: the only progress indicator lived inside Paper Studio, on the
 * one screen they had just walked away from. The natural reading of a silent
 * app is that the run died.
 *
 * So the tracker lives in the app shell. It is deliberately small — a pill, not
 * a banner — because it is ambient status, not a thing to act on. Clicking it
 * returns to the paper being written, which is the only action it needs.
 *
 * It renders nothing when no run is in flight, so it costs a subscription and
 * nothing else on every other screen.
 */

import { useRouter } from "next/navigation";

import { Spinner } from "@/components/ui/spinner";
import { useEditorStore } from "@/store/editor-store";
import { cn } from "@/lib/utils";

export function GenerationTracker({ className }: { className?: string }) {
  const router = useRouter();
  const activeRun = useEditorStore((s) => s.activeRun);

  if (!activeRun) return null;

  const { produced, total, paperId, phase } = activeRun;

  // A count is only shown once the blueprint has declared how many questions
  // there will be. Before that, `produced` on its own reads as progress toward
  // an unknown finish and tells the teacher nothing they can use.
  const hasCount = total > 0;
  const label = hasCount
    ? `${produced}/${total} questions`
    : phase || "Writing your paper";

  const goToPaper = () => {
    router.push(paperId ? `/editor?paperId=${paperId}` : "/editor");
  };

  return (
    <button
      type="button"
      onClick={goToPaper}
      title={`${phase || "Writing your paper"} — click to open the paper`}
      aria-label={`Generation in progress: ${label}. Open the paper.`}
      className={cn(
        "inline-flex items-center gap-2 rounded-full border border-border bg-muted/40 px-3 py-1",
        "text-[11.5px] font-medium text-muted-foreground transition-colors",
        "hover:border-foreground/30 hover:bg-muted hover:text-foreground",
        className,
      )}
    >
      <Spinner className="size-3" />
      <span className="tabular-nums">{label}</span>
      {hasCount ? (
        // A hairline bar rather than a percentage: the pool over-generates and
        // the count can move in jumps, so a precise-looking number invites a
        // trust it has not earned.
        <span
          aria-hidden
          className="hidden h-1 w-10 overflow-hidden rounded-full bg-border sm:block"
        >
          <span
            className="block h-full rounded-full bg-primary transition-[width] duration-500"
            style={{
              width: `${Math.min(100, Math.round((produced / total) * 100))}%`,
            }}
          />
        </span>
      ) : null}
    </button>
  );
}
