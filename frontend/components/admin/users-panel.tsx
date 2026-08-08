"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  approveMember,
  assignMemberToOrganization,
  changeMemberRole,
  rejectMember,
  removeMember,
  type OrganizationSummary,
} from "@/lib/organizations-client";
import { listPlatformUsers, type PlatformUser } from "@/lib/users-client";

const statusVariant: Record<
  PlatformUser["status"],
  "secondary" | "default" | "destructive" | "outline"
> = {
  pending: "secondary",
  approved: "default",
  admin: "outline",
  rejected: "destructive",
};

const PAGE_SIZE = 50;

/**
 * Every user on the platform, with their school, role and standing editable
 * in place.
 *
 * Role and school both live on the *membership*, not the account, which is why
 * a user with no school has neither picker — there is nothing to change until
 * they belong somewhere. Assigning them a school is what creates that row, so
 * the school picker is the one control that is offered either way.
 */
export function UsersPanel({
  currentUserId,
  organizations,
}: {
  currentUserId?: string;
  /** Schools available as a move/assign target. */
  organizations: OrganizationSummary[];
}) {
  const [users, setUsers] = useState<PlatformUser[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async (q: string, nextOffset: number) => {
    setLoading(true);
    try {
      const page = await listPlatformUsers({ q, limit: PAGE_SIZE, offset: nextOffset });
      setUsers(page.users);
      setTotal(page.total);
    } catch (err: any) {
      toast.error(err?.message || "Failed to load users");
    } finally {
      setLoading(false);
    }
  }, []);

  // Debounced: the search hits the server (so it can match rows on pages this
  // one isn't showing), and a request per keystroke would be wasteful.
  useEffect(() => {
    const handle = setTimeout(() => void load(query, offset), query ? 300 : 0);
    return () => clearTimeout(handle);
  }, [load, query, offset]);

  /** Replace one row in place, leaving the rest of the page untouched. */
  const patchRow = (userId: string, patch: Partial<PlatformUser>) =>
    setUsers((rows) => rows.map((r) => (r.id === userId ? { ...r, ...patch } : r)));

  /**
   * Every action shares this shape: mark the row busy, run it, report what
   * happened, clear busy. Errors surface the backend's own wording — refusals
   * like "this is the school's only admin" are written for this reader.
   */
  const run = async (userId: string, fn: () => Promise<void>) => {
    setBusyId(userId);
    try {
      await fn();
    } catch (err: any) {
      toast.error(err?.message || "That didn't work");
    } finally {
      setBusyId(null);
    }
  };

  const who = (user: PlatformUser) => user.name || user.email;

  const handleRoleChange = (user: PlatformUser, role: "org_admin" | "teacher") =>
    run(user.id, async () => {
      if (!user.membership) return;
      const updated = await changeMemberRole(
        user.membership.organization_id,
        user.id,
        role,
      );
      patchRow(user.id, { membership: { ...user.membership, role: updated.role } });
      toast.success(
        `${who(user)} is now a ${role === "org_admin" ? "school admin" : "teacher"} — we've emailed them`,
      );
    });

  const handleAssign = (user: PlatformUser, organizationId: string) => {
    const target = organizations.find((o) => o.id === organizationId);
    if (!target) return;
    // Moving someone between schools is a bigger step than the role picker
    // beside it, and both are one click — so this one asks first.
    const verb = user.membership
      ? `Move ${who(user)} from ${user.membership.organization_name} to ${target.name}?`
      : `Add ${who(user)} to ${target.name}?`;
    if (!confirm(`${verb} They'll be emailed about it.`)) return;

    return run(user.id, async () => {
      const updated = await assignMemberToOrganization(user.id, organizationId);
      patchRow(user.id, {
        membership: {
          organization_id: organizationId,
          organization_name: target.name,
          role: updated.role,
          status: updated.status,
        },
      });
      toast.success(
        updated.status === "approved"
          ? `${who(user)} moved to ${target.name} — we've emailed them`
          : `${who(user)} added to ${target.name}, pending approval — we've emailed them`,
      );
    });
  };

  const handleApprove = (user: PlatformUser) =>
    run(user.id, async () => {
      if (!user.membership) return;
      const updated = await approveMember(user.membership.organization_id, user.id);
      patchRow(user.id, {
        status: "approved",
        membership: { ...user.membership, status: updated.status },
      });
      toast.success(`${who(user)} approved — we've emailed them`);
    });

  const handleReject = (user: PlatformUser) =>
    run(user.id, async () => {
      if (!user.membership) return;
      const updated = await rejectMember(user.membership.organization_id, user.id);
      patchRow(user.id, {
        status: "rejected",
        membership: { ...user.membership, status: updated.status },
      });
      toast.success(`${who(user)} rejected — we've emailed them`);
    });

  const handleRemove = (user: PlatformUser) => {
    if (!user.membership) return;
    if (
      !confirm(
        `Remove ${who(user)} from ${user.membership.organization_name}? ` +
          `Their account stays, but they'll have no school. They'll be emailed about it.`,
      )
    )
      return;

    return run(user.id, async () => {
      await removeMember(user.membership!.organization_id, user.id);
      // The row stays — the user still exists, they just have no school now.
      patchRow(user.id, { status: "pending", membership: null });
      toast.success(`${who(user)} removed — we've emailed them`);
    });
  };

  const showingTo = Math.min(offset + PAGE_SIZE, total);

  return (
    <div className="space-y-4">
      <Input
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          // A new search invalidates the current page number.
          setOffset(0);
        }}
        placeholder="Search by name or email"
        className="max-w-sm"
      />

      {loading ? (
        <div className="flex justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : users.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted-foreground">
          {query ? "No users match that search." : "No users yet."}
        </p>
      ) : (
        <>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>School</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Tokens</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((user) => {
                  const busy = busyId === user.id;
                  const isSelf = user.id === currentUserId;
                  const membership = user.membership;
                  // The superadmin belongs to no school by design; offering to
                  // file them under one would be offering to break them.
                  const movable = !user.is_superadmin && !isSelf;

                  return (
                    <TableRow key={user.id}>
                      <TableCell>{user.name || "—"}</TableCell>
                      <TableCell>{user.email}</TableCell>

                      <TableCell>
                        {!movable ? (
                          <span className="text-sm text-muted-foreground">
                            {user.is_superadmin
                              ? "Platform"
                              : membership?.organization_name ?? "No school yet"}
                          </span>
                        ) : (
                          <Select
                            value={membership?.organization_id ?? ""}
                            onValueChange={(value) => {
                              const next = value as string;
                              if (next && next !== membership?.organization_id) {
                                void handleAssign(user, next);
                              }
                            }}
                            disabled={busy}
                          >
                            <SelectTrigger size="sm" className="w-[170px]">
                              <SelectValue placeholder="No school yet" />
                            </SelectTrigger>
                            <SelectContent>
                              {organizations.map((org) => (
                                <SelectItem key={org.id} value={org.id}>
                                  {org.name}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        )}
                      </TableCell>

                      <TableCell>
                        {!membership ? (
                          <span className="text-sm text-muted-foreground">
                            {user.is_superadmin ? "Superadmin" : "—"}
                          </span>
                        ) : isSelf ? (
                          // The backend refuses this anyway; a picker that can
                          // only fail is worse than showing the value.
                          <span
                            className="text-sm text-muted-foreground"
                            title="You cannot change your own role."
                          >
                            {membership.role === "org_admin" ? "School admin" : "Teacher"}
                          </span>
                        ) : (
                          <Select
                            value={membership.role}
                            onValueChange={(value) => {
                              const next = value as "org_admin" | "teacher";
                              if (next && next !== membership.role) {
                                void handleRoleChange(user, next);
                              }
                            }}
                            disabled={busy}
                          >
                            <SelectTrigger size="sm" className="w-[150px]">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="teacher">Teacher</SelectItem>
                              <SelectItem value="org_admin">School admin</SelectItem>
                            </SelectContent>
                          </Select>
                        )}
                      </TableCell>

                      <TableCell>
                        <Badge variant={statusVariant[user.status]}>{user.status}</Badge>
                      </TableCell>

                      {/* tabular-nums: a numeric column that has to align. */}
                      <TableCell className="text-right tabular-nums">
                        {user.tokens_consumed.toLocaleString()}
                      </TableCell>

                      <TableCell className="text-right">
                        {!membership || isSelf ? (
                          // Approve/reject/remove all act on a membership. With
                          // no school there is nothing to act on — assign them
                          // one first, via the School column.
                          <span className="text-xs text-muted-foreground">—</span>
                        ) : (
                          <div className="flex justify-end gap-2">
                            {membership.status !== "approved" && (
                              <Button
                                size="sm"
                                variant="outline"
                                disabled={busy}
                                onClick={() => void handleApprove(user)}
                              >
                                Approve
                              </Button>
                            )}
                            {membership.status !== "rejected" && (
                              <Button
                                size="sm"
                                variant="outline"
                                disabled={busy}
                                onClick={() => void handleReject(user)}
                              >
                                Reject
                              </Button>
                            )}
                            <Button
                              size="sm"
                              variant="destructive"
                              disabled={busy}
                              onClick={() => void handleRemove(user)}
                            >
                              Remove
                            </Button>
                          </div>
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>

          {total > PAGE_SIZE && (
            <div className="flex items-center justify-between text-sm text-muted-foreground">
              <span>
                {offset + 1}–{showingTo} of {total}
              </span>
              <div className="space-x-2">
                <button
                  type="button"
                  className="rounded border px-2 py-1 disabled:opacity-50"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                >
                  Previous
                </button>
                <button
                  type="button"
                  className="rounded border px-2 py-1 disabled:opacity-50"
                  disabled={showingTo >= total}
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
