"use client";

import { useState } from "react";
import { toast } from "sonner";

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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  approveMember,
  changeMemberRole,
  rejectMember,
  removeMember,
  type OrganizationMember,
} from "@/lib/organizations-client";

const statusVariant: Record<OrganizationMember["status"], "secondary" | "default" | "destructive"> = {
  pending: "secondary",
  approved: "default",
  rejected: "destructive",
};

/** The stored slugs are not what a school administrator should be reading. */
const roleLabel: Record<OrganizationMember["role"], string> = {
  org_admin: "School admin",
  teacher: "Teacher",
};

export function MembersTable({
  orgId,
  members,
  onChange,
  /**
   * The signed-in user's id, when known. Used only to grey out their own role
   * picker — the backend refuses the change regardless, this just avoids
   * offering an action that can only fail.
   */
  currentUserId,
}: {
  orgId: string;
  members: OrganizationMember[];
  onChange: (members: OrganizationMember[]) => void;
  currentUserId?: string;
}) {
  const [busyId, setBusyId] = useState<string | null>(null);

  // Demoting the last admin strands the school with nobody able to approve
  // teachers, so the backend rejects it. Counting here lets the row explain
  // that before the click rather than after.
  const approvedAdminCount = members.filter(
    (m) => m.role === "org_admin" && m.status === "approved",
  ).length;

  const handleApprove = async (userId: string) => {
    setBusyId(userId);
    try {
      const updated = await approveMember(orgId, userId);
      onChange(members.map((m) => (m.user_id === userId ? updated : m)));
      toast.success("Member approved — we've emailed them");
    } catch (err: any) {
      toast.error(err?.message || "Failed to approve member");
    } finally {
      setBusyId(null);
    }
  };

  const handleReject = async (userId: string) => {
    setBusyId(userId);
    try {
      const updated = await rejectMember(orgId, userId);
      onChange(members.map((m) => (m.user_id === userId ? updated : m)));
      toast.success("Member rejected — we've emailed them");
    } catch (err: any) {
      toast.error(err?.message || "Failed to reject member");
    } finally {
      setBusyId(null);
    }
  };

  const handleRoleChange = async (userId: string, role: OrganizationMember["role"]) => {
    setBusyId(userId);
    try {
      const updated = await changeMemberRole(orgId, userId, role);
      onChange(members.map((m) => (m.user_id === userId ? updated : m)));
      toast.success(`Role changed to ${roleLabel[role].toLowerCase()} — we've emailed them`);
    } catch (err: any) {
      // The backend's refusals ("this is the school's only admin") are written
      // for this reader, so they go through unedited.
      toast.error(err?.message || "Failed to change role");
    } finally {
      setBusyId(null);
    }
  };

  const handleRemove = async (userId: string) => {
    if (!confirm("Remove this user from the organization? They'll be emailed about it.")) return;
    setBusyId(userId);
    try {
      await removeMember(orgId, userId);
      onChange(members.filter((m) => m.user_id !== userId));
      toast.success("Member removed — we've emailed them");
    } catch (err: any) {
      toast.error(err?.message || "Failed to remove member");
    } finally {
      setBusyId(null);
    }
  };

  if (members.length === 0) {
    return <p className="text-sm text-muted-foreground py-6 text-center">No members yet.</p>;
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Email</TableHead>
          <TableHead>Role</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Tokens used</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {members.map((member) => {
          const isSelf = member.user_id === currentUserId;
          const isLastAdmin = member.role === "org_admin" && approvedAdminCount <= 1;
          // Two rows must keep their admin: your own, and the school's last
          // one. Everything else is freely re-rolable.
          const roleLocked = isSelf || isLastAdmin;
          const busy = busyId === member.user_id;

          return (
            <TableRow key={member.id}>
              <TableCell>{member.name}</TableCell>
              <TableCell>{member.email}</TableCell>
              <TableCell>
                {roleLocked ? (
                  <span
                    className="text-sm text-muted-foreground"
                    title={
                      isSelf
                        ? "You cannot change your own role — ask another admin."
                        : "The school's only admin. Promote someone else first."
                    }
                  >
                    {roleLabel[member.role]}
                  </span>
                ) : (
                  <Select
                    value={member.role}
                    onValueChange={(value) => {
                      const next = value as OrganizationMember["role"];
                      if (next && next !== member.role) {
                        void handleRoleChange(member.user_id, next);
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
                <Badge variant={statusVariant[member.status]}>{member.status}</Badge>
              </TableCell>
              <TableCell>{member.tokens_consumed.toLocaleString()}</TableCell>
              <TableCell className="text-right space-x-2">
                {member.status !== "approved" && !isSelf && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy}
                    onClick={() => handleApprove(member.user_id)}
                  >
                    Approve
                  </Button>
                )}
                {member.status !== "rejected" && !isSelf && !isLastAdmin && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy}
                    onClick={() => handleReject(member.user_id)}
                  >
                    Reject
                  </Button>
                )}
                {!isSelf && !isLastAdmin && (
                  <Button
                    size="sm"
                    variant="destructive"
                    disabled={busy}
                    onClick={() => handleRemove(member.user_id)}
                  >
                    Remove
                  </Button>
                )}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
