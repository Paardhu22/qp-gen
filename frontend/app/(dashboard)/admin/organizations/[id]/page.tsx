"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { toast } from "sonner";
import { ArrowLeft } from "lucide-react";
import { Spinner } from "@/components/ui/spinner";

import { useSession, isSuperAdmin } from "@/lib/auth-client";
import {
  formatInr,
  getOrganization,
  type OrganizationDetail,
} from "@/lib/organizations-client";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { PageTitle } from "@/components/ui/page-title";
import { MembersTable } from "@/components/admin/members-table";
import { TeacherInvites } from "@/components/admin/teacher-invites";
import { SchoolDomains } from "@/components/admin/school-domains";

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
        <Spinner size="page" />
      </div>
    );
  }

  if (!isSuperAdmin(user)) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-2">
        <PageTitle>Admin access required</PageTitle>
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
          <Spinner size="page" />
        </div>
      ) : (
        <>
          <div>
            <PageTitle>{org.name}</PageTitle>
            <p className="text-sm text-muted-foreground">
              {org.member_count} users · {org.total_tokens.toLocaleString()} tokens used
              {" · "}
              {formatInr(org.total_cost_inr)} estimated
              {org.monthly_token_limit > 0 &&
                ` · capped at ${org.monthly_token_limit.toLocaleString()} tokens a month`}
            </p>
            {org.email_domains.length > 0 && (
              <p className="mt-1 text-xs text-muted-foreground">
                Matches staff email at {org.email_domains.join(", ")}
              </p>
            )}
          </div>

          <TeacherInvites orgId={org.id} />

          <SchoolDomains org={org} onSaved={setOrg} />

          <Card>
            <CardHeader>
              <CardTitle>Members</CardTitle>
              <CardDescription>Approve, reject, or remove users in this school.</CardDescription>
            </CardHeader>
            <CardContent>
              <MembersTable
                orgId={org.id}
                members={org.members}
                onChange={(members) => setOrg({ ...org, members })}
              />
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
