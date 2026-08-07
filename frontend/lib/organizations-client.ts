import { fetchJson } from "@/lib/api-client";

export type PublicOrganization = {
  id: string;
  name: string;
};

export type OrganizationSummary = {
  id: string;
  name: string;
  slug: string;
  is_active: boolean;
  created_at: string;
  member_count: number;
  total_tokens: number;
  admin_email: string | null;
};

export type OrganizationMember = {
  id: string;
  user_id: string;
  name: string;
  email: string;
  role: "org_admin" | "teacher";
  status: "pending" | "approved" | "rejected";
  created_at: string;
  tokens_consumed: number;
};

export type OrganizationDetail = OrganizationSummary & {
  members: OrganizationMember[];
};

export type OrganizationUsageSummary = {
  total_tokens: number;
  unassigned_tokens: number;
  organizations: OrganizationSummary[];
};

/** Public, unauthenticated: the org dropdown shown at signup. */
export async function listPublicOrganizations(): Promise<PublicOrganization[]> {
  return fetchJson<PublicOrganization[]>("/api/organizations/public", {
    method: "GET",
    skipAuth: true,
  });
}

/** Teacher signup: request to join an org. Membership starts pending. */
export async function joinOrganization(organizationId: string): Promise<void> {
  await fetchJson("/api/organizations/join", {
    method: "POST",
    body: JSON.stringify({ organization_id: organizationId }),
  });
}

/** Public: look up the email an org-admin invite was sent to, by token. */
export async function getOrganizationInvite(token: string): Promise<{ email: string }> {
  return fetchJson<{ email: string }>(
    `/api/organizations/invites/accept?token=${encodeURIComponent(token)}`,
    { method: "GET", skipAuth: true },
  );
}

/** Invited org admin: accept the invite and create the organization. */
export async function acceptOrganizationInvite(
  token: string,
  organizationName: string,
): Promise<OrganizationDetail> {
  return fetchJson<OrganizationDetail>("/api/organizations/invites/accept", {
    method: "POST",
    body: JSON.stringify({ token, organization_name: organizationName }),
  });
}

/** Superadmin: invite an email to create + administer a new organization. */
export async function sendOrganizationInvite(email: string): Promise<void> {
  await fetchJson("/api/organizations/invites", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

/** Superadmin: every organization, with member count + token usage. */
export async function listOrganizations(): Promise<OrganizationSummary[]> {
  // Trailing slash is required: the route is path("") under "api/organizations/",
  // and the project sets APPEND_SLASH = False, so the slashless form is a hard
  // 404 rather than a redirect.
  return fetchJson<OrganizationSummary[]>("/api/organizations/", { method: "GET" });
}

/** Superadmin: platform-wide token usage rollup. */
export async function getUsageSummary(): Promise<OrganizationUsageSummary> {
  return fetchJson<OrganizationUsageSummary>("/api/organizations/usage", { method: "GET" });
}

/** Org admin (own org) or superadmin: organization detail + members. */
export async function getOrganization(orgId: string): Promise<OrganizationDetail> {
  return fetchJson<OrganizationDetail>(`/api/organizations/${orgId}`, { method: "GET" });
}

/** Org admin (own org) or superadmin: members list with usage. */
export async function listMembers(orgId: string): Promise<OrganizationMember[]> {
  return fetchJson<OrganizationMember[]>(`/api/organizations/${orgId}/members`, { method: "GET" });
}

export async function approveMember(orgId: string, userId: string): Promise<OrganizationMember> {
  return fetchJson<OrganizationMember>(`/api/organizations/${orgId}/members/${userId}/approve`, {
    method: "POST",
  });
}

export async function rejectMember(orgId: string, userId: string): Promise<OrganizationMember> {
  return fetchJson<OrganizationMember>(`/api/organizations/${orgId}/members/${userId}/reject`, {
    method: "POST",
  });
}

export async function removeMember(orgId: string, userId: string): Promise<void> {
  await fetchJson<void>(`/api/organizations/${orgId}/members/${userId}`, {
    method: "DELETE",
  });
}
