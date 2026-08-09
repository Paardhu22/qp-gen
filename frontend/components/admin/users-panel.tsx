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
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
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
  deletePlatformUser,
  rejectMember,
  removeMember,
  setPlatformSuperadmin,
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
 * What the Role picker holds. Superadmin sits on the account and the other two
 * sit on the membership, so this is not simply `Membership["role"]` — "none" is
 * the real state of an account that belongs to no school yet.
 */
type RoleValue = "superadmin" | "org_admin" | "teacher" | "none";

const roleValue = (user: PlatformUser): RoleValue =>
  user.is_superadmin ? "superadmin" : (user.membership?.role as RoleValue) ?? "none";

const ROLE_LABELS: Record<RoleValue, string> = {
  superadmin: "Superadmin",
  org_admin: "School admin",
  teacher: "Teacher",
  none: "No school role",
};

const roleLabel = (user: PlatformUser) => ROLE_LABELS[roleValue(user)];

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
  // The two actions that ask before they act share one dialog: only ever one
  // can be pending, and a per-row dialog would mean one mounted per user.
  const [pending, setPending] = useState<{
    title: string;
    description: string;
    confirmLabel: string;
    destructive?: boolean;
    /**
     * When set, the confirm button stays disabled until this exact text is
     * typed. Reserved for the one action here that destroys data no backup of
     * ours can return — a click alone is too cheap for it.
     */
    confirmPhrase?: string;
    act: () => void;
  } | null>(null);
  const [typed, setTyped] = useState("");

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

  /**
   * Grant or revoke platform superadmin. Always confirmed: unlike the other
   * two roles this one is not scoped to a school, and each direction has a
   * consequence the picker alone doesn't show — granting ends their school
   * membership, revoking leaves them with no school at all.
   */
  const handleSuperadmin = (user: PlatformUser, grant: boolean) =>
    setPending({
      title: grant ? "Make them a superadmin?" : "Remove superadmin access?",
      description: grant
        ? `${who(user)} will be able to see every school, invite new ones, and ` +
          `manage any account.` +
          (user.membership
            ? ` Their membership of ${user.membership.organization_name} ends, ` +
              `since superadmins work across all schools.`
            : "") +
          " They'll be emailed about it."
        : `${who(user)} will lose access to every school, and won't belong to ` +
          `one until you assign them a school. They'll be emailed about it.`,
      confirmLabel: grant ? "Make superadmin" : "Remove access",
      destructive: !grant,
      act: () =>
        void run(user.id, async () => {
          await setPlatformSuperadmin(user.id, grant);
          patchRow(user.id, {
            is_superadmin: grant,
            status: grant ? "admin" : "pending",
            // Granting ends the membership; revoking leaves them school-less
            // either way, so both directions clear it.
            membership: null,
          });
          toast.success(
            grant
              ? `${who(user)} is now a superadmin — we've emailed them`
              : `${who(user)} is no longer a superadmin — we've emailed them`,
          );
        }),
    });

  const handleAssign = (user: PlatformUser, organizationId: string) => {
    const target = organizations.find((o) => o.id === organizationId);
    if (!target) return;
    // Moving someone between schools is a bigger step than the role picker
    // beside it, and both are one click — so this one asks first.
    setPending({
      title: user.membership ? "Move to another school?" : "Add to a school?",
      description: user.membership
        ? `${who(user)} will move from ${user.membership.organization_name} to ${target.name}. They'll be emailed about it.`
        : `${who(user)} will be added to ${target.name}. They'll be emailed about it.`,
      confirmLabel: user.membership ? "Move" : "Add",
      act: () =>
        void run(user.id, async () => {
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
        }),
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
    setPending({
      title: `Remove from ${user.membership.organization_name}?`,
      description:
        `${who(user)}'s account stays, but they'll have no school until someone ` +
        `assigns them one. They'll be emailed about it.`,
      confirmLabel: "Remove",
      destructive: true,
      act: () =>
        void run(user.id, async () => {
          await removeMember(user.membership!.organization_id, user.id);
          // The row stays — the user still exists, they just have no school now.
          patchRow(user.id, { status: "pending", membership: null });
          toast.success(`${who(user)} removed — we've emailed them`);
        }),
    });
  };

  /**
   * Delete the account itself — Cognito included — rather than its membership.
   *
   * Confirmed by typing the email, because nothing here can undo it: the
   * credentials are gone from Cognito and the papers, projects and questions
   * are deleted with the row.
   */
  const handleDelete = (user: PlatformUser) =>
    setPending({
      title: "Delete this account?",
      description:
        `${who(user)} will be deleted from the sign-in directory and from ` +
        `qp-gen, along with every paper, project and question they saved. ` +
        `This cannot be undone. Type their email to confirm.`,
      confirmLabel: "Delete account",
      destructive: true,
      confirmPhrase: user.email,
      act: () =>
        void run(user.id, async () => {
          await deletePlatformUser(user.id);
          setUsers((rows) => rows.filter((r) => r.id !== user.id));
          setTotal((n) => Math.max(0, n - 1));
          toast.success(`${who(user)}'s account was deleted`);
        }),
    });

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
                              {/* Children, not a placeholder: the primitive
                                  renders the raw value, and the value here is
                                  an organization id nobody can read. */}
                              <SelectValue>
                                {membership?.organization_name ?? (
                                  <span className="text-muted-foreground">
                                    No school yet
                                  </span>
                                )}
                              </SelectValue>
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
                        {isSelf ? (
                          // The backend refuses this anyway; a picker that can
                          // only fail is worse than showing the value.
                          <span
                            className="text-sm text-muted-foreground"
                            title="You cannot change your own role."
                          >
                            {roleLabel(user)}
                          </span>
                        ) : (
                          <Select
                            value={roleValue(user)}
                            onValueChange={(value) => {
                              const next = value as RoleValue;
                              if (!next || next === roleValue(user)) return;
                              if (next === "superadmin") {
                                handleSuperadmin(user, true);
                              } else if (roleValue(user) === "superadmin") {
                                // The only way down from superadmin: they have
                                // no school, so there is no in-school role to
                                // land in until one is assigned.
                                handleSuperadmin(user, false);
                              } else {
                                void handleRoleChange(user, next as "org_admin" | "teacher");
                              }
                            }}
                            disabled={busy}
                          >
                            <SelectTrigger size="sm" className="w-[150px]">
                              {/* Children, not a bare <SelectValue />: the
                                  primitive renders the stored slug otherwise. */}
                              <SelectValue>{roleLabel(user)}</SelectValue>
                            </SelectTrigger>
                            <SelectContent>
                              {/* Teacher and school admin live on a membership,
                                  so they are only offered to someone who has
                                  one. Superadmin is a property of the account
                                  and is always available. */}
                              {membership && !user.is_superadmin && (
                                <>
                                  <SelectItem value="teacher">Teacher</SelectItem>
                                  <SelectItem value="org_admin">School admin</SelectItem>
                                </>
                              )}
                              {(user.is_superadmin || !membership) && (
                                <SelectItem value="none">No school role</SelectItem>
                              )}
                              <SelectItem value="superadmin">Superadmin</SelectItem>
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
                        <div className="flex justify-end gap-2">
                          {/* Approve, reject and remove all act on a
                              membership — with no school there is nothing for
                              them to act on. Deleting the account doesn't:
                              it's the one action that reaches a user who
                              belongs nowhere, which is exactly the row an
                              admin most often wants rid of. */}
                          {membership && !isSelf && (
                            <>
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
                                variant="outline"
                                disabled={busy}
                                onClick={() => void handleRemove(user)}
                              >
                                Remove from school
                              </Button>
                            </>
                          )}
                          {/* Not offered for yourself, and not for another
                              superadmin — revoke their access first, so ending
                              platform staff's account is two deliberate steps. */}
                          {!isSelf && !user.is_superadmin ? (
                            <Button
                              size="sm"
                              variant="destructive"
                              disabled={busy}
                              onClick={() => handleDelete(user)}
                            >
                              Delete account
                            </Button>
                          ) : (
                            !membership && (
                              <span className="text-xs text-muted-foreground">—</span>
                            )
                          )}
                        </div>
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

      <AlertDialog
        open={pending !== null}
        onOpenChange={(open) => {
          if (!open) {
            setPending(null);
            setTyped("");
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{pending?.title}</AlertDialogTitle>
            <AlertDialogDescription>{pending?.description}</AlertDialogDescription>
          </AlertDialogHeader>
          {pending?.confirmPhrase && (
            <Input
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              placeholder={pending.confirmPhrase}
              autoComplete="off"
              aria-label={`Type ${pending.confirmPhrase} to confirm`}
            />
          )}
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className={pending?.destructive ? buttonVariants({ variant: "destructive" }) : undefined}
              disabled={
                !!pending?.confirmPhrase && typed.trim() !== pending.confirmPhrase
              }
              onClick={() => pending?.act()}
            >
              {pending?.confirmLabel}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
