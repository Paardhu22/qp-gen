/** Date wording for the Papers library. */

export function formatDate(value?: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

/**
 * "Today", "Yesterday", "3 days ago" for the first fortnight, the plain date
 * after that. A card that says "Oct 4, 2026" makes the teacher do the
 * arithmetic; "6 days ago" answers the question they actually have.
 */
export function formatRelative(value?: string | null, now = Date.now()): string {
  if (!value) return "—";
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return "—";
  const days = Math.floor((now - then) / 86_400_000);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 14) return `${days} days ago`;
  return formatDate(value);
}
