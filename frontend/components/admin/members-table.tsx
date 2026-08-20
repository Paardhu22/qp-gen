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
  approveMember,
  formatInr,
  rejectMember,
  removeMember,
  type OrganizationMember,
} from "@/lib/organizations-client";

const statusVariant: Record<OrganizationMember["status"], "secondary" | "default" | "destructive"> = {
  pending: "secondary",
  approved: "default",
  rejected: "destructive",
};

export function MembersTable({
  orgId,
  members,
  onChange,
}: {
  orgId: string;
  members: OrganizationMember[];
  onChange: (members: OrganizationMember[]) => void;
}) {
  const [busyId, setBusyId] = useState<string | null>(null);

  const handleApprove = async (userId: string) => {
    setBusyId(userId);
    try {
      const updated = await approveMember(orgId, userId);
      onChange(members.map((m) => (m.user_id === userId ? updated : m)));
      toast.success("Member approved");
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
      toast.success("Member rejected");
    } catch (err: any) {
      toast.error(err?.message || "Failed to reject member");
    } finally {
      setBusyId(null);
    }
  };

  const handleRemove = async (userId: string) => {
    if (!confirm("Remove this user from the organization?")) return;
    setBusyId(userId);
    try {
      await removeMember(orgId, userId);
      onChange(members.filter((m) => m.user_id !== userId));
      toast.success("Member removed");
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
          <TableHead className="text-right">Tokens used</TableHead>
          <TableHead className="text-right">Est. spend</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {members.map((member) => (
          <TableRow key={member.id}>
            <TableCell>{member.name}</TableCell>
            <TableCell>{member.email}</TableCell>
            <TableCell className="capitalize">{member.role.replace("_", " ")}</TableCell>
            <TableCell>
              <Badge variant={statusVariant[member.status]}>{member.status}</Badge>
            </TableCell>
            {/* tabular-nums on both: these are columns being scanned for
                magnitude, not standalone figures. */}
            <TableCell className="text-right tabular-nums">
              {member.tokens_consumed.toLocaleString()}
            </TableCell>
            <TableCell className="text-right tabular-nums">
              {formatInr(member.cost_inr)}
            </TableCell>
            <TableCell className="text-right space-x-2">
              {member.status !== "approved" && member.role !== "org_admin" && (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busyId === member.user_id}
                  onClick={() => handleApprove(member.user_id)}
                >
                  Approve
                </Button>
              )}
              {member.status !== "rejected" && member.role !== "org_admin" && (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busyId === member.user_id}
                  onClick={() => handleReject(member.user_id)}
                >
                  Reject
                </Button>
              )}
              {member.role !== "org_admin" && (
                <Button
                  size="sm"
                  variant="destructive"
                  disabled={busyId === member.user_id}
                  onClick={() => handleRemove(member.user_id)}
                >
                  Remove
                </Button>
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
