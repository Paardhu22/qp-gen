"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";

import { useSession, isSuperAdmin, isOrgAdmin } from "@/lib/auth-client";
import {
  listOrganizations,
  sendOrganizationInvite,
  getOrganization,
  getSuperAdminAnalytics,
  type OrganizationSummary,
  type OrganizationDetail,
  type SuperAdminAnalytics,
} from "@/lib/organizations-client";
import { UsageAnalytics } from "@/components/admin/usage-analytics";
import { RosterPanel } from "@/components/admin/roster-panel";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { MembersTable } from "@/components/admin/members-table";
import { UsersPanel } from "@/components/admin/users-panel";
import { Loader2, Mail } from "lucide-react";

function InviteOrganizationDialog({ onInvited }: { onInvited: () => void }) {
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await sendOrganizationInvite(email.trim());
      toast.success(`Invite sent to ${email.trim()}`);
      setEmail("");
      setOpen(false);
      onInvited();
    } catch (err: any) {
      toast.error(err?.message || "Failed to send invite");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button><Mail className="h-4 w-4" />Invite organization</Button>} />
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Invite a new school</DialogTitle>
          <DialogDescription>
            We&apos;ll email a link where they set up their account and organization.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleInvite} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="invite-email">Admin email</Label>
            <Input
              id="invite-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="principal@school.edu"
              required
            />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={loading}>
              {loading ? "Sending…" : "Send invite"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function SuperAdminDashboard({ currentUserId }: { currentUserId?: string }) {
  const [orgs, setOrgs] = useState<OrganizationSummary[]>([]);
  const [analytics, setAnalytics] = useState<SuperAdminAnalytics | null>(null);
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (windowDays: number) => {
    setLoading(true);
    try {
      // Both in flight together: the table and the charts are one screen, and
      // serialising them would show the page assembling itself in two stages.
      const [orgList, stats] = await Promise.all([
        listOrganizations(),
        getSuperAdminAnalytics(windowDays),
      ]);
      setOrgs(orgList);
      setAnalytics(stats);
    } catch (err: any) {
      toast.error(err?.message || "Failed to load the dashboard");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(days);
  }, [load, days]);

  return (
    <div className="max-w-6xl mx-auto w-full p-4 sm:p-6 space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Platform</h1>
          <p className="text-sm text-muted-foreground">
            Usage, schools, and everything waiting on you.
          </p>
        </div>
        <InviteOrganizationDialog onInvited={() => void load(days)} />
      </div>

      {analytics && (
        <>
          <UsageAnalytics data={analytics} days={days} onDaysChange={setDays} />
          <RosterPanel roster={analytics.roster} />
        </>
      )}

      <Card>
        <CardHeader>
          <CardTitle>All schools</CardTitle>
          <CardDescription>
            The same usage data as the chart above, readable row by row.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : orgs.length === 0 ? (
            <p className="text-sm text-muted-foreground py-6 text-center">
              No organizations yet. Invite a school to get started.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>School</TableHead>
                  <TableHead>Admin</TableHead>
                  <TableHead>Members</TableHead>
                  <TableHead className="text-right">Tokens used</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {orgs.map((org) => (
                  <TableRow key={org.id}>
                    <TableCell className="font-medium">
                      <div className="flex items-center gap-2.5">
                        {org.logo_url ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={org.logo_url}
                            alt=""
                            className="h-7 w-7 shrink-0 rounded object-contain"
                          />
                        ) : (
                          <span
                            aria-hidden
                            className="flex h-7 w-7 shrink-0 items-center justify-center rounded bg-muted text-[11px] font-medium text-muted-foreground"
                          >
                            {org.name.slice(0, 2).toUpperCase()}
                          </span>
                        )}
                        <div className="min-w-0">
                          <p className="truncate">{org.name}</p>
                          {org.city && (
                            <p className="truncate text-xs font-normal text-muted-foreground">
                              {[org.city, org.state].filter(Boolean).join(", ")}
                            </p>
                          )}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>{org.admin_email || "—"}</TableCell>
                    <TableCell>{org.member_count}</TableCell>
                    {/* tabular-nums: this one IS a column that must align. */}
                    <TableCell className="text-right tabular-nums">
                      {org.total_tokens.toLocaleString()}
                    </TableCell>
                    <TableCell className="text-right">
                      <Link href={`/admin/organizations/${org.id}`}>
                        <Button size="sm" variant="outline">
                          Manage
                        </Button>
                      </Link>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>All users</CardTitle>
          <CardDescription>
            Everyone on the platform. Move them between schools, change their
            role, approve or remove them — each one emails the user.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <UsersPanel currentUserId={currentUserId} organizations={orgs} />
        </CardContent>
      </Card>
    </div>
  );
}

function OrgAdminDashboard({
  organizationId,
  currentUserId,
}: {
  organizationId: string;
  currentUserId?: string;
}) {
  const [org, setOrg] = useState<OrganizationDetail | null>(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      setOrg(await getOrganization(organizationId));
    } catch (err: any) {
      toast.error(err?.message || "Failed to load organization");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [organizationId]);

  if (loading) {
    return (
      <div className="flex justify-center py-16">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!org) return null;

  return (
    <div className="max-w-5xl mx-auto w-full p-4 sm:p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">{org.name}</h1>
        <p className="text-sm text-muted-foreground">
          {org.member_count} users · {org.total_tokens.toLocaleString()} tokens used
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Members</CardTitle>
          <CardDescription>
            Approve, reject, or remove teachers, and move them between teacher and
            school admin. Every change is emailed to them.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <MembersTable
            orgId={org.id}
            members={org.members}
            currentUserId={currentUserId}
            onChange={(members) => setOrg({ ...org, members })}
          />
        </CardContent>
      </Card>
    </div>
  );
}

export default function AdminPage() {
  const { data: session, isLoading } = useSession();
  const user = session?.user;

  if (isLoading) {
    return (
      <div className="flex justify-center py-16">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (isSuperAdmin(user)) {
    return <SuperAdminDashboard currentUserId={user?.id} />;
  }

  if (isOrgAdmin(user) && user?.membership) {
    return (
      <OrgAdminDashboard
        organizationId={user.membership.organization_id}
        currentUserId={user.id}
      />
    );
  }

  return (
    <div className="flex flex-col items-center justify-center py-16 gap-2">
      <h1 className="text-xl font-semibold text-foreground">Admin access required</h1>
      <p className="text-sm text-muted-foreground">You don&apos;t have permission to view this page.</p>
    </div>
  );
}
