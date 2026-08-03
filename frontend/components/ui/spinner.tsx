import { Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * The app's only spinner. Two sizes on purpose:
 *
 * - `default` (size-4) sits inline, inside a button or beside a label.
 * - `page` (size-8) centres itself in whatever box it is given and is for a
 *   route or panel that has nothing to show yet.
 *
 * A skeleton beats a spinner whenever the shape of the incoming content is
 * known — reach for `SkeletonRows` for lists and tables.
 */
function Spinner({
  size = "default",
  label,
  className,
}: {
  size?: "default" | "page";
  label?: string;
  className?: string;
}) {
  const icon = (
    <Loader2
      className={cn(
        "animate-spin",
        // An inline spinner almost always sits inside text that is already the
        // right colour — a button label, a status line — so it inherits rather
        // than forcing muted, which would wash out on a `bg-primary` button.
        size === "page" ? "size-8 text-muted-foreground" : "size-4 text-current",
        className,
      )}
    />
  );

  if (size !== "page") return icon;

  return (
    <div
      role="status"
      aria-live="polite"
      className="flex h-full flex-1 items-center justify-center"
    >
      <div className="text-center">
        {icon}
        {label ? (
          <p className="mt-3 text-sm text-muted-foreground">{label}</p>
        ) : (
          <span className="sr-only">Loading</span>
        )}
      </div>
    </div>
  );
}

export { Spinner };
