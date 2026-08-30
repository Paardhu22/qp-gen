"use client";

/**
 * Teacher invites: the way into a school that skips the approval queue.
 *
 * The default path asks a teacher to find their school in a dropdown of every
 * school on the platform, send a request, and wait for someone to notice. Each
 * of those three steps is a place an onboarding dies — most often the middle
 * one, where the wrong "St. Mary's" gets picked and the request lands in a
 * queue nobody at that school will ever action.
 *
 * An invite collapses all three. It is safe to skip approval here precisely
 * because the person issuing the link is the person who would have approved
 * the request; the backend re-checks that the address on the invite is the
 * address that signed up, so a forwarded link is not a way in.
 */

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { MailPlus, X } from "lucide-react";
import { Spinner } from "@/components/ui/spinner";
import {
  inviteTeacher,
  listTeacherInvites,
  revokeOrganizationInvite,
  type OrganizationInvite,
} from "@/lib/organizations-client";

const STATUS_LABEL: Record<OrganizationInvite["effective_status"], string> = {
  pending: "Waiting",
  accepted: "Joined",
  expired: "Expired",
  revoked: "Withdrawn",
};

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
  });
}

export function TeacherInvites({ orgId }: { orgId: string }) {
  const [invites, setInvites] = useState<OrganizationInvite[]>([]);
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setInvites(await listTeacherInvites(orgId));
    } catch (err: any) {
      toast.error(err?.message || "Could not load your invites");
    } finally {
      setLoading(false);
    }
  }, [orgId]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    const address = email.trim();
    if (!address) return;
    setSending(true);
    try {
      await inviteTeacher(orgId, address);
      setEmail("");
      toast.success(`Invite sent to ${address}`);
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Could not send that invite");
    } finally {
      setSending(false);
    }
  };

  const handleRevoke = async (invite: OrganizationInvite) => {
    setBusyId(invite.id);
    try {
      await revokeOrganizationInvite(invite.id);
      toast.success(`The invite to ${invite.email} no longer works`);
      await load();
    } catch (err: any) {
      toast.error(err?.message || "Could not withdraw that invite");
    } finally {
      setBusyId(null);
    }
  };

  // Withdrawn and expired invites are history, not a to-do list. They stay
  // reachable in the API, but a panel that accumulates every dead link stops
  // showing the two that still matter.
  const visible = invites.filter(
    (i) => i.effective_status === "pending" || i.effective_status === "accepted",
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <MailPlus className="h-4 w-4 text-muted-foreground" aria-hidden />
          Invite a teacher
        </CardTitle>
        <CardDescription>
          They join straight away — no request to approve, and no school to pick
          from a list.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form onSubmit={handleInvite} className="flex flex-col gap-2 sm:flex-row">
          <Input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="teacher@yourschool.edu"
            aria-label="Teacher's email address"
            required
          />
          <Button type="submit" disabled={sending} className="shrink-0">
            {sending ? "Sending…" : "Send invite"}
          </Button>
        </form>

        {loading ? (
          <div className="flex justify-center py-4">
            <Spinner size="page" />
          </div>
        ) : visible.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No invites outstanding.
          </p>
        ) : (
          <div className="space-y-2">
            {visible.map((invite) => (
              <div
                key={invite.id}
                className="flex items-center justify-between gap-3 rounded-lg border border-border p-2.5"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-foreground">
                    {invite.email}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Sent {formatDate(invite.created_at)}
                    {invite.effective_status === "pending" &&
                      ` · expires ${formatDate(invite.expires_at)}`}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  <Badge
                    variant={
                      invite.effective_status === "accepted" ? "default" : "secondary"
                    }
                  >
                    {STATUS_LABEL[invite.effective_status]}
                  </Badge>
                  {invite.effective_status === "pending" && (
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-7 w-7"
                      title={`Withdraw the invite to ${invite.email}`}
                      aria-label={`Withdraw the invite to ${invite.email}`}
                      disabled={busyId === invite.id}
                      onClick={() => void handleRevoke(invite)}
                    >
                      <X className="h-3.5 w-3.5" aria-hidden />
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
