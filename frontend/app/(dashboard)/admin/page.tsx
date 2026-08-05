"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";

import { useSession, isSuperAdmin, isOrgAdmin } from "@/lib/auth-client";
import {
  listOrganizations,
  sendOrganizationInvite,
  getOrganization,
  type OrganizationSummary,
  type OrganizationDetail,
} from "@/lib/organizations-client";
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

function SuperAdminDashboard() {
  const [orgs, setOrgs] = useState<OrganizationSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      setOrgs(await listOrganizations());
    } catch (err: any) {
      toast.error(err?.message || "Failed to load organizations");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const totalTokens = orgs.reduce((sum, o) => sum + o.total_tokens, 0);
  const totalMembers = orgs.reduce((sum, o) => sum + o.member_count, 0);

  return (
    <div className="max-w-5xl mx-auto w-full p-4 sm:p-6 space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Organizations</h1>
          <p className="text-sm text-muted-foreground">
            {orgs.length} schools · {totalMembers} users · {totalTokens.toLocaleString()} tokens used
          </p>
        </div>
        <InviteOrganizationDialog onInvited={load} />
      </div>

      <Card>
        <CardContent className="pt-4">
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
                  <TableHead>Tokens used</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {orgs.map((org) => (
                  <TableRow key={org.id}>
                    <TableCell className="font-medium">{org.name}</TableCell>
                    <TableCell>{org.admin_email || "—"}</TableCell>
                    <TableCell>{org.member_count}</TableCell>
                    <TableCell>{org.total_tokens.toLocaleString()}</TableCell>
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
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (isSuperAdmin(user)) {
    return <SuperAdminDashboard />;
  }

  if (isOrgAdmin(user) && user?.membership) {
    return <OrgAdminDashboard organizationId={user.membership.organization_id} />;
  }

  return (
    <div className="flex flex-col items-center justify-center py-16 gap-2">
      <h1 className="text-xl font-semibold text-foreground">Admin access required</h1>
      <p className="text-sm text-muted-foreground">You don&apos;t have permission to view this page.</p>
    </div>
  );
}
