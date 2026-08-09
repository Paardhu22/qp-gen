"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { toast } from "sonner";
import { ArrowLeft, Loader2 } from "lucide-react";

import { useSession, isSuperAdmin } from "@/lib/auth-client";
import { getOrganization, type OrganizationDetail } from "@/lib/organizations-client";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { MembersTable } from "@/components/admin/members-table";

export default function OrganizationDetailPage() {
  const params = useParams<{ id: string }>();
  const orgId = params.id;
  const { data: session, isLoading: sessionLoading } = useSession();
  const user = session?.user;

  const [org, setOrg] = useState<OrganizationDetail | null>(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      setOrg(await getOrganization(orgId));
    } catch (err: any) {
      toast.error(err?.message || "Failed to load organization");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isSuperAdmin(user)) load();
  }, [orgId, user]);

  if (sessionLoading) {
    return (
      <div className="flex justify-center py-16">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!isSuperAdmin(user)) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-2">
        <h1 className="text-xl font-semibold text-foreground">Admin access required</h1>
        <p className="text-sm text-muted-foreground">You don&apos;t have permission to view this page.</p>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto w-full p-4 sm:p-6 space-y-6">
      <Link href="/admin" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" />
        Back to organizations
      </Link>

      {loading || !org ? (
        <div className="flex justify-center py-16">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <>
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
                Approve, reject, or remove users in this school, and move them
                between teacher and school admin. Every change is emailed to them.
                Select a name to see the papers they&apos;ve generated.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <MembersTable
                orgId={org.id}
                members={org.members}
                currentUserId={user?.id}
                onChange={(members) => setOrg({ ...org, members })}
              />
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
