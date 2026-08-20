"use client";

/**
 * The operational half of the superadmin dashboard: what is waiting on someone
 * to act, rather than what has already happened.
 *
 * Deliberately not charts. "Three invites expire on Friday" is a to-do list,
 * and a bar chart of it would be decoration over a list you still have to read.
 */

import { useState } from "react";
import Link from "next/link";
import { toast } from "sonner";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AlertTriangle, Clock, MailWarning, UserPlus, X } from "lucide-react";
import { revokeOrganizationInvite, type SuperAdminAnalytics } from "@/lib/organizations-client";

function daysUntil(iso: string): number {
  const ms = new Date(iso).getTime() - Date.now();
  return Math.ceil(ms / 86_400_000);
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function RosterPanel({
  roster,
  onChange,
}: {
  roster: SuperAdminAnalytics["roster"];
  /** Called after a revoke, so the dashboard can refetch. */
  onChange?: () => void;
}) {
  const { expired_invite_count, pending_members, empty_organizations } = roster;
  // Revoked rows leave the list immediately rather than waiting on a refetch:
  // the button's whole purpose is "this link should stop working now", and a
  // row that lingers reads as though it did not.
  const [revoked, setRevoked] = useState<string[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);
  const pending_invites = roster.pending_invites.filter((i) => !revoked.includes(i.id));

  const handleRevoke = async (inviteId: string, email: string) => {
    setBusyId(inviteId);
    try {
      await revokeOrganizationInvite(inviteId);
      setRevoked((ids) => [...ids, inviteId]);
      toast.success(`The invite to ${email} no longer works`);
      onChange?.();
    } catch (err: any) {
      toast.error(err?.message || "Could not withdraw that invite");
    } finally {
      setBusyId(null);
    }
  };

  const nothingWaiting =
    pending_invites.length === 0 &&
    pending_members.length === 0 &&
    empty_organizations.length === 0 &&
    expired_invite_count === 0;

  if (nothingWaiting) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Nothing waiting</CardTitle>
          <CardDescription>
            No pending invites, no approvals to make, and every school has members.
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      {pending_members.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <UserPlus className="h-4 w-4 text-muted-foreground" aria-hidden />
              Awaiting approval
            </CardTitle>
            <CardDescription>
              Teachers who asked to join a school and need a decision.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {pending_members.map((m) => (
              <div
                key={m.id}
                className="flex items-center justify-between gap-3 rounded-lg border border-border p-2.5"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-foreground">{m.name || m.email}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    {m.email} · {m.organization_name}
                  </p>
                </div>
                <Link href={`/admin/organizations/${m.organization_id}`}>
                  <Button size="sm" variant="outline">
                    Review
                  </Button>
                </Link>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {(pending_invites.length > 0 || expired_invite_count > 0) && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Clock className="h-4 w-4 text-muted-foreground" aria-hidden />
              Invites not yet accepted
            </CardTitle>
            <CardDescription>
              {expired_invite_count > 0
                ? `${expired_invite_count} more have expired unused.`
                : "Sent, but the school has not signed up yet."}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {pending_invites.map((inv) => {
              const left = daysUntil(inv.expires_at);
              // Icon + label, never colour alone — the status palette rule.
              const soon = left <= 2;
              return (
                <div
                  key={inv.id}
                  className="flex items-center justify-between gap-3 rounded-lg border border-border p-2.5"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-foreground">{inv.email}</p>
                    <p className="text-xs text-muted-foreground">
                      Sent {formatDate(inv.created_at)}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <Badge variant={soon ? "destructive" : "secondary"} className="gap-1">
                      {soon && <MailWarning className="h-3 w-3" aria-hidden />}
                      {left <= 0 ? "Expired" : `${left}d left`}
                    </Badge>
                    {/* An invite is a live credential for a week. A typo'd
                        address or someone who has left the school is exactly
                        the case where the link is in the wrong inbox, and
                        waiting it out was the only remedy before this. */}
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-7 w-7"
                      title={`Withdraw the invite to ${inv.email}`}
                      aria-label={`Withdraw the invite to ${inv.email}`}
                      disabled={busyId === inv.id}
                      onClick={() => void handleRevoke(inv.id, inv.email)}
                    >
                      <X className="h-3.5 w-3.5" aria-hidden />
                    </Button>
                  </div>
                </div>
              );
            })}
            {pending_invites.length === 0 && (
              <p className="text-sm text-muted-foreground">
                All {expired_invite_count} outstanding invites have expired. Send a fresh one.
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {empty_organizations.length > 0 && (
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-muted-foreground" aria-hidden />
              Schools with no teachers yet
            </CardTitle>
            <CardDescription>
              Onboarded, but nobody beyond the admin has joined — the ones worth a follow-up call.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {empty_organizations.map((o) => (
              <Link key={o.id} href={`/admin/organizations/${o.id}`}>
                <Badge variant="outline" className="cursor-pointer gap-1.5 py-1">
                  {o.name}
                  <span className="text-muted-foreground">· {formatDate(o.created_at)}</span>
                </Badge>
              </Link>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
