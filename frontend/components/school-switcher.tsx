"use client";

/**
 * Which school you are working as, when you belong to more than one.
 *
 * A teacher can hold memberships at several schools — a subject specialist
 * covering two branches, someone mid-move between jobs — but at any moment
 * they are working as exactly one: one masthead on the paper, one budget the
 * tokens come out of, one set of colleagues in the admin screens.
 *
 * Switching moves nothing. Papers, question banks and templates stay with the
 * account that made them; what changes is the school the next paper is branded
 * and billed as. That is worth saying in the UI, because "switch school" reads
 * like it might take your work somewhere else.
 *
 * Renders nothing at all for the overwhelming majority of accounts, which
 * belong to one school. A picker with one option is a control that only ever
 * costs the reader a moment.
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { Check, Loader2 } from "lucide-react";
import { approvedMemberships, type SessionUser } from "@/lib/auth-client";
import { switchOrganization } from "@/lib/organizations-client";
import { cn } from "@/lib/utils";

export function SchoolSwitcher({
  user,
  onSwitched,
  className,
}: {
  user?: SessionUser | null;
  /** Called after a successful switch — refresh the session here. */
  onSwitched?: () => void | Promise<void>;
  className?: string;
}) {
  const router = useRouter();
  const [busyId, setBusyId] = useState<string | null>(null);
  const schools = approvedMemberships(user);
  const activeId = user?.membership?.organization_id ?? null;

  if (schools.length < 2) return null;

  const handleSwitch = async (organizationId: string, name: string) => {
    if (organizationId === activeId) return;
    setBusyId(organizationId);
    try {
      await switchOrganization(organizationId);
      await onSwitched?.();
      toast.success(`Now working as ${name}`);
      // The papers list, brand header and admin screens are all scoped by the
      // active school, so the current view is stale the moment this succeeds.
      router.refresh();
    } catch (err: any) {
      toast.error(err?.message || "Could not switch school");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className={cn("px-2 py-1.5", className)}>
      <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        Working as
      </p>
      <div className="space-y-0.5">
        {schools.map((school) => {
          const active = school.organization_id === activeId;
          return (
            <button
              key={school.organization_id}
              type="button"
              disabled={busyId !== null}
              onClick={() =>
                void handleSwitch(school.organization_id, school.organization_name)
              }
              aria-current={active ? "true" : undefined}
              className={cn(
                "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors",
                active
                  ? "bg-accent font-medium text-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground",
                busyId !== null && "opacity-60",
              )}
            >
              {busyId === school.organization_id ? (
                <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" aria-hidden />
              ) : (
                // Icon, not colour alone, carries "this is the one".
                <Check
                  className={cn("h-3.5 w-3.5 shrink-0", !active && "opacity-0")}
                  aria-hidden
                />
              )}
              <span className="min-w-0 flex-1 truncate">
                {school.organization_name}
              </span>
              {school.role === "org_admin" && (
                <span className="shrink-0 text-[10px] uppercase tracking-wide text-muted-foreground">
                  Admin
                </span>
              )}
            </button>
          );
        })}
      </div>
      <p className="mt-1 px-2 text-[10.5px] text-muted-foreground/80">
        Your papers stay where they are — this changes the school new work is
        branded and billed as.
      </p>
    </div>
  );
}
