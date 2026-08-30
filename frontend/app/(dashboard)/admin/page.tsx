"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";

import { useSession, isSuperAdmin, approvedAdminMemberships } from "@/lib/auth-client";
import {
  formatInr,
  listOrganizations,
  sendOrganizationInvite,
  getOrganization,
  getSuperAdminAnalytics,
  setMonthlyTokenLimit,
  type OrganizationSummary,
  type OrganizationDetail,
  type SuperAdminAnalytics,
} from "@/lib/organizations-client";
import { UsageAnalytics } from "@/components/admin/usage-analytics";
import { RosterPanel } from "@/components/admin/roster-panel";
import { TeacherInvites } from "@/components/admin/teacher-invites";
import { SchoolDomains } from "@/components/admin/school-domains";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { PageTitle } from "@/components/ui/page-title";
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
import { resolveFigureSrc } from "@/components/editor/extensions/float-image";
import { Mail } from "lucide-react";
import { Spinner } from "@/components/ui/spinner";

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

function SpendCapDialog({
  org,
  onSaved,
}: {
  org: OrganizationSummary;
  onSaved: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState(String(org.monthly_token_limit || 0));
  const [saving, setSaving] = useState(false);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    const limit = Number(value);
    if (!Number.isFinite(limit) || limit < 0) {
      toast.error("Enter a whole number of tokens, or 0 for no cap.");
      return;
    }
    setSaving(true);
    try {
      await setMonthlyTokenLimit(org.id, Math.floor(limit));
      toast.success(
        limit === 0
          ? `${org.name} now has no monthly cap`
          : `${org.name} is capped at ${Math.floor(limit).toLocaleString()} tokens a month`,
      );
      setOpen(false);
      onSaved();
    } catch (err: any) {
      toast.error(err?.message || "Could not save that limit");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button size="sm" variant="ghost">
            {org.monthly_token_limit > 0
              ? `${compactTokens(org.monthly_token_limit)} cap`
              : "No cap"}
          </Button>
        }
      />
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Monthly limit for {org.name}</DialogTitle>
          <DialogDescription>
            Once this school&apos;s usage for the calendar month reaches the limit,
            new generation is blocked until the month rolls over. Zero means no cap.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSave} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="token-limit">Tokens per month</Label>
            <Input
              id="token-limit"
              type="number"
              min={0}
              step={1000}
              value={value}
              onChange={(e) => setValue(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              This school has used {org.total_tokens.toLocaleString()} tokens in
              total, about {formatInr(org.total_cost_inr)}.
            </p>
          </div>
          <DialogFooter>
            <Button type="submit" disabled={saving}>
              {saving ? "Saving…" : "Save limit"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** Short token counts for a control label, where 4,000,000 will not fit. */
function compactTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n % 1_000_000 === 0 ? 0 : 1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(n % 1_000 === 0 ? 0 : 1)}k`;
  return String(n);
}

function SuperAdminDashboard() {
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
          <PageTitle>Platform</PageTitle>
          <p className="text-sm text-muted-foreground">
            Usage, schools, and everything waiting on you.
          </p>
        </div>
        <InviteOrganizationDialog onInvited={() => void load(days)} />
      </div>

      {analytics && (
        <>
          <UsageAnalytics data={analytics} days={days} onDaysChange={setDays} />
          <RosterPanel roster={analytics.roster} onChange={() => void load(days)} />
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
              <Spinner size="page" />
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
                  <TableHead className="text-right">Est. spend</TableHead>
                  <TableHead className="text-right">Monthly cap</TableHead>
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
                            src={resolveFigureSrc(org.logo_url)}
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
                    {/* An estimate — see formatInr. The column header says
                        "Est." rather than leaving the reader to assume it will
                        reconcile against an invoice. */}
                    <TableCell className="text-right tabular-nums">
                      {formatInr(org.total_cost_inr)}
                    </TableCell>
                    <TableCell className="text-right">
                      <SpendCapDialog org={org} onSaved={() => void load(days)} />
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
    </div>
  );
}

function OrgAdminDashboard({ organizationId }: { organizationId: string }) {
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
        <Spinner size="page" />
      </div>
    );
  }

  if (!org) return null;

  return (
    <div className="max-w-5xl mx-auto w-full p-4 sm:p-6 space-y-6">
      <div>
        <PageTitle>{org.name}</PageTitle>
        <p className="text-sm text-muted-foreground">
          {org.member_count} users · {org.total_tokens.toLocaleString()} tokens used
          {" · "}
          {formatInr(org.total_cost_inr)} estimated
          {org.monthly_token_limit > 0 &&
            ` · capped at ${org.monthly_token_limit.toLocaleString()} tokens a month`}
        </p>
      </div>

      <TeacherInvites orgId={org.id} />

      <SchoolDomains org={org} onSaved={setOrg} />

      <Card>
        <CardHeader>
          <CardTitle>Members</CardTitle>
          <CardDescription>Approve, reject, or remove teachers from your school.</CardDescription>
        </CardHeader>
        <CardContent>
          <MembersTable
            orgId={org.id}
            members={org.members}
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
        <Spinner size="page" />
      </div>
    );
  }

  if (isSuperAdmin(user)) {
    return <SuperAdminDashboard />;
  }

  // Multi-org: an admin of two schools manages the one they are working as.
  // The other is a switch away in the navbar — which is the same control that
  // decides brand and billing, so there is only ever one place to change it.
  const adminSchools = approvedAdminMemberships(user);
  const activeAdminSchool =
    adminSchools.find(
      (m) => m.organization_id === user?.membership?.organization_id,
    ) ?? adminSchools[0];
  if (activeAdminSchool) {
    return (
      <OrgAdminDashboard organizationId={activeAdminSchool.organization_id} />
    );
  }

  return (
    <div className="flex flex-col items-center justify-center py-16 gap-2">
      <PageTitle>Admin access required</PageTitle>
      <p className="text-sm text-muted-foreground">You don&apos;t have permission to view this page.</p>
    </div>
  );
}
