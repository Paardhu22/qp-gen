import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * A placeholder block for content that has not arrived yet.
 *
 * Invariants the app relies on — keep them here rather than at the call site:
 * one fill (`bg-muted/40`), one animation (`animate-pulse`), and a radius on
 * the theme scale. Callers override size, never appearance.
 */
function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      aria-hidden
      className={cn("animate-pulse rounded-lg bg-muted/40", className)}
      {...props}
    />
  );
}

/**
 * The placeholder for a loading table or list.
 *
 * `height` must match the real row it stands in for — a skeleton that is the
 * wrong height moves the page when the data lands, which is the whole thing
 * skeletons exist to prevent.
 */
function SkeletonRows({
  rows = 10,
  height = "h-9",
  className,
}: {
  rows?: number;
  height?: string;
  className?: string;
}) {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label="Loading"
      className={cn("space-y-1 p-4", className)}
    >
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className={height} />
      ))}
    </div>
  );
}

export { Skeleton, SkeletonRows };
