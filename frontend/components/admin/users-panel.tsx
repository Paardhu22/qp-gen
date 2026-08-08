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
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { changeMemberRole } from "@/lib/organizations-client";
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
 * Every user on the platform, in one table, with their role editable in place.
 *
 * Roles are a property of the *membership*, not the account, so the picker
 * writes through the organization endpoint — which is also what makes it
 * absent for a user who has not joined a school yet. There is nothing to
 * change until they belong somewhere.
 */
export function UsersPanel({ currentUserId }: { currentUserId?: string }) {
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

  const handleRoleChange = async (user: PlatformUser, role: "org_admin" | "teacher") => {
    if (!user.membership) return;
    setBusyId(user.id);
    try {
      const updated = await changeMemberRole(user.membership.organization_id, user.id, role);
      setUsers((rows) =>
        rows.map((row) =>
          row.id === user.id && row.membership
            ? { ...row, membership: { ...row.membership, role: updated.role } }
            : row,
        ),
      );
      toast.success(
        `${user.name || user.email} is now a ${
          role === "org_admin" ? "school admin" : "teacher"
        } — we've emailed them`,
      );
    } catch (err: any) {
      toast.error(err?.message || "Failed to change role");
    } finally {
      setBusyId(null);
    }
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
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>School</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Tokens used</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.map((user) => (
                <TableRow key={user.id}>
                  <TableCell>{user.name || "—"}</TableCell>
                  <TableCell>{user.email}</TableCell>
                  <TableCell>
                    {user.membership?.organization_name ?? (
                      <span className="text-muted-foreground">
                        {user.is_superadmin ? "Platform" : "No school yet"}
                      </span>
                    )}
                  </TableCell>
                  <TableCell>
                    {!user.membership ? (
                      <span className="text-sm text-muted-foreground">
                        {user.is_superadmin ? "Superadmin" : "—"}
                      </span>
                    ) : user.id === currentUserId ? (
                      // The backend refuses this anyway; showing a picker that
                      // can only fail would be worse than showing the value.
                      <span className="text-sm text-muted-foreground" title="You cannot change your own role.">
                        {user.membership.role === "org_admin" ? "School admin" : "Teacher"}
                      </span>
                    ) : (
                      <Select
                        value={user.membership.role}
                        onValueChange={(value) => {
                          const next = value as "org_admin" | "teacher";
                          if (next && next !== user.membership?.role) {
                            void handleRoleChange(user, next);
                          }
                        }}
                        disabled={busyId === user.id}
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
                </TableRow>
              ))}
            </TableBody>
          </Table>

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
