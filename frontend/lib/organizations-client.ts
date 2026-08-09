import { fetchForm, fetchJson } from "@/lib/api-client";

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
  logo_url: string | null;
  city: string;
  state: string;
};

/**
 * The institute profile. Every field is optional — onboarding step 2 can be
 * skipped, so any consumer has to treat "" as "not supplied" rather than
 * rendering an empty row.
 */
export type OrganizationProfile = {
  address_line1: string;
  address_line2: string;
  city: string;
  state: string;
  postal_code: string;
  country: string;
  phone: string;
  website: string;
  gstin: string;
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

export type OrganizationDetail = OrganizationSummary &
  OrganizationProfile & {
    members: OrganizationMember[];
    logo_width: number | null;
    logo_height: number | null;
  };

export type OrganizationUsageSummary = {
  total_tokens: number;
  unassigned_tokens: number;
  organizations: OrganizationSummary[];
};

/** One day of the trend chart. Zero-filled by the backend across the window. */
export type UsagePoint = {
  date: string;
  tokens: number;
  calls: number;
};

export type UsageSlice = {
  label: string;
  tokens: number;
  calls: number;
};

export type OrganizationUsageRow = {
  id: string;
  name: string;
  city: string;
  is_active: boolean;
  tokens: number;
  calls: number;
  member_count: number;
};

export type PendingMember = {
  id: string;
  user_id: string;
  name: string;
  email: string;
  organization_id: string;
  organization_name: string;
  created_at: string;
};

/** Everything the superadmin dashboard draws, in one round trip. */
export type SuperAdminAnalytics = {
  days: number;
  totals: {
    total_tokens: number;
    prompt_tokens: number;
    completion_tokens: number;
    unassigned_tokens: number;
    organization_count: number;
    active_organization_count: number;
    member_count: number;
    pending_member_count: number;
  };
  trend: UsagePoint[];
  by_organization: OrganizationUsageRow[];
  by_operation: UsageSlice[];
  by_model: UsageSlice[];
  roster: {
    pending_invites: { id: string; email: string; status: string; created_at: string; expires_at: string }[];
    expired_invite_count: number;
    pending_members: PendingMember[];
    empty_organizations: { id: string; name: string; created_at: string }[];
  };
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

/**
 * Invited org admin: accept the invite and create the organization.
 *
 * `profile` carries whatever step 2 collected. It is optional in every sense —
 * omitted entirely when the admin skipped the step, and individually blank for
 * any field they left alone.
 */
export async function acceptOrganizationInvite(
  token: string,
  organizationName: string,
  profile?: Partial<OrganizationProfile>,
): Promise<OrganizationDetail> {
  return fetchJson<OrganizationDetail>("/api/organizations/invites/accept", {
    method: "POST",
    body: JSON.stringify({
      token,
      organization_name: organizationName,
      ...(profile ?? {}),
    }),
  });
}

/** Org admin or superadmin: edit the institute profile after onboarding. */
export async function updateOrganization(
  orgId: string,
  patch: Partial<OrganizationProfile & { name: string }>,
): Promise<OrganizationDetail> {
  return fetchJson<OrganizationDetail>(`/api/organizations/${orgId}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

/** Upload the school crest. Multipart — see OrganizationLogoView. */
export async function uploadOrganizationLogo(
  orgId: string,
  file: File,
): Promise<OrganizationDetail> {
  const form = new FormData();
  form.append("file", file);
  return fetchForm<OrganizationDetail>(`/api/organizations/${orgId}/logo`, form);
}

/** Remove the crest. Idempotent — safe when none was ever uploaded. */
export async function deleteOrganizationLogo(orgId: string): Promise<OrganizationDetail> {
  return fetchJson<OrganizationDetail>(`/api/organizations/${orgId}/logo`, {
    method: "DELETE",
  });
}

/** Superadmin: every dashboard panel in one request. `days` sizes the trend. */
export async function getSuperAdminAnalytics(days = 30): Promise<SuperAdminAnalytics> {
  return fetchJson<SuperAdminAnalytics>(`/api/organizations/analytics?days=${days}`, {
    method: "GET",
  });
}

/** Superadmin: invite an email to create + administer a new organization. */
export async function sendOrganizationInvite(email: string): Promise<void> {
  await fetchJson("/api/organizations/invites", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

/**
 * Superadmin: expire a sent invite early, so its link stops working.
 *
 * The invite row survives as a record of what was sent — only its status and
 * deadline change — so the caller should drop it from the pending list rather
 * than expect it back as something still actionable.
 */
export async function revokeOrganizationInvite(inviteId: string): Promise<void> {
  await fetchJson(`/api/organizations/invites/${inviteId}/revoke`, {
    method: "POST",
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

export type MemberPaper = {
  id: string;
  title: string;
  subject: string | null;
  grade_class: string | null;
  board: string | null;
  /** How many variants (Set A, Set B, …) were generated for this paper. */
  set_count: number;
  created_at: string;
};

/**
 * Org admin (own org) or superadmin: what one member has generated.
 *
 * Metadata only — titles, subjects and dates, never the question text. The
 * question this answers is "what has this teacher been producing", and the
 * paper contents are a much larger disclosure than that.
 */
export async function listMemberPapers(
  orgId: string,
  userId: string,
): Promise<{ user: { id: string; name: string; email: string }; papers: MemberPaper[] }> {
  return fetchJson(`/api/organizations/${orgId}/members/${userId}/papers`, {
    method: "GET",
  });
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

/**
 * Move a member between teacher and school admin. The backend refuses a few
 * cases the UI cannot know about on its own — demoting the school's only admin,
 * changing your own role — so the error message is worth surfacing verbatim.
 */
export async function changeMemberRole(
  orgId: string,
  userId: string,
  role: OrganizationMember["role"],
): Promise<OrganizationMember> {
  return fetchJson<OrganizationMember>(`/api/organizations/${orgId}/members/${userId}/role`, {
    method: "POST",
    body: JSON.stringify({ role }),
  });
}

/**
 * Superadmin: put a user in a school, or move them to a different one.
 *
 * One call covers both because they differ only in whether a membership
 * already exists — the common case (an account that signed up and never
 * joined anywhere) has no source school to address the request to.
 *
 * `role` defaults to teacher server-side: administering one school says
 * nothing about the next.
 */
export async function assignMemberToOrganization(
  userId: string,
  organizationId: string,
  role?: OrganizationMember["role"],
): Promise<OrganizationMember> {
  return fetchJson<OrganizationMember>(`/api/organizations/members/${userId}/assign`, {
    method: "POST",
    body: JSON.stringify({ organization_id: organizationId, ...(role ? { role } : {}) }),
  });
}

export async function removeMember(orgId: string, userId: string): Promise<void> {
  await fetchJson<void>(`/api/organizations/${orgId}/members/${userId}`, {
    method: "DELETE",
  });
}
