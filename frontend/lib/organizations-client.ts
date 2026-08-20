import { fetchForm, fetchJson } from "@/lib/api-client";

export type PublicOrganization = {
  id: string;
  name: string;
  city: string;
  /**
   * True when the signup email's domain is one this school claims.
   *
   * A hint for the picker and nothing more — the membership still starts
   * pending and still needs an admin's approval. Domains are trivially
   * spoofable at signup, so this may only reorder a list that was already
   * public.
   */
  matches_email_domain: boolean;
};

export type OrganizationSummary = {
  id: string;
  name: string;
  slug: string;
  is_active: boolean;
  created_at: string;
  member_count: number;
  total_tokens: number;
  /**
   * Estimated rupee spend, all time. An ESTIMATE — our token counts cannot see
   * cached-input discounts or image-token tiers — so every surface that shows
   * it must say so. See `formatInr`.
   */
  total_cost_inr: number;
  monthly_token_limit: number;
  admin_email: string | null;
  logo_url: string | null;
  city: string;
  state: string;
  /** Email domains this school's staff addresses end in. */
  email_domains: string[];
};

/**
 * The institute profile. Every field is optional — onboarding step 2 can be
 * skipped, so any consumer has to treat "" as "not supplied" rather than
 * rendering an empty row.
 */
export type OrganizationProfile = {
  /**
   * Comma-separated on the way in (that is what the settings field collects),
   * an array on the way out. The backend normalises and rejects public
   * providers — see apps/organizations/domains.py.
   */
  email_domains: string;
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
  /** Estimated rupee spend for this member. See `total_cost_inr`. */
  cost_inr: number;
};

export type OrganizationDetail = Omit<OrganizationProfile, "email_domains"> &
  OrganizationSummary & {
    members: OrganizationMember[];
    logo_width: number | null;
    logo_height: number | null;
  };

/** One invite, as the admin screens list it. The token is never sent. */
export type OrganizationInvite = {
  id: string;
  email: string;
  role: "org_admin" | "teacher";
  status: "pending" | "accepted" | "expired" | "revoked";
  /**
   * `status`, corrected for an invite whose date has passed but whose column
   * has not been settled yet. This is the one to render.
   */
  effective_status: "pending" | "accepted" | "expired" | "revoked";
  organization: string | null;
  organization_name: string | null;
  invited_by_email: string | null;
  created_at: string;
  expires_at: string;
};

/** What a `?token=` lookup tells the signup screen before anyone signs up. */
export type InvitePreview = {
  email: string;
  role: "org_admin" | "teacher";
  organization_id: string | null;
  organization_name: string | null;
};

export type OrganizationUsageSummary = {
  total_tokens: number;
  unassigned_tokens: number;
  total_cost_inr: number;
  unassigned_cost_inr: number;
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
  cost_inr: number;
};

export type OrganizationUsageRow = {
  id: string;
  name: string;
  city: string;
  is_active: boolean;
  tokens: number;
  calls: number;
  cost_inr: number;
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
    total_cost_inr: number;
    unassigned_cost_inr: number;
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
    pending_invites: OrganizationInvite[];
    expired_invite_count: number;
    pending_members: PendingMember[];
    empty_organizations: { id: string; name: string; created_at: string }[];
  };
};

/**
 * Public, unauthenticated: the org dropdown shown at signup.
 *
 * Pass the teacher's email and the school claiming that domain comes back
 * first, flagged. That is the difference between confirming a choice and
 * hunting through an alphabetical list of every school on the platform —
 * picking the wrong one strands the teacher in a pending queue nobody at that
 * school will action.
 */
export async function listPublicOrganizations(
  email?: string,
): Promise<PublicOrganization[]> {
  const query = email?.includes("@") ? `?email=${encodeURIComponent(email)}` : "";
  return fetchJson<PublicOrganization[]>(`/api/organizations/public${query}`, {
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

/**
 * Public: what an invite token is for, before anyone has signed up.
 *
 * Returns the address it was sent to plus the role, so the signup screen can
 * say what accepting actually does. A teacher told to "set up your
 * organization" reasonably thinks they are being asked to register their
 * school a second time.
 */
export async function getOrganizationInvite(token: string): Promise<InvitePreview> {
  return fetchJson<InvitePreview>(
    `/api/organizations/invites/accept?token=${encodeURIComponent(token)}`,
    { method: "GET", skipAuth: true },
  );
}

/**
 * Invited teacher: accept and join the school already approved.
 *
 * No organization is named — the school comes off the invite. A client that
 * could name its own would turn any valid teacher invite into membership of
 * any school on the platform.
 */
export async function acceptTeacherInvite(token: string): Promise<void> {
  await fetchJson("/api/organizations/invites/accept", {
    method: "POST",
    body: JSON.stringify({ token }),
  });
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

/** Superadmin: every invite ever sent. `status=open` for the live ones. */
export async function listOrganizationInvites(
  status?: "open" | OrganizationInvite["status"],
): Promise<OrganizationInvite[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return fetchJson<OrganizationInvite[]>(`/api/organizations/invites${query}`, {
    method: "GET",
  });
}

/**
 * Withdraw an invite that has not been accepted.
 *
 * An invite is a live credential for seven days, and the two cases that
 * produce a bad one — a typo'd address, and a person who has since left the
 * school — are exactly the cases where the link is in an inbox it should not
 * be in. Superadmin for org-creation invites; a school's own admin for their
 * school's teacher invites.
 */
export async function revokeOrganizationInvite(
  inviteId: string,
): Promise<OrganizationInvite> {
  return fetchJson<OrganizationInvite>(`/api/organizations/invites/${inviteId}`, {
    method: "DELETE",
  });
}

/** Org admin: teacher invites issued for this school. */
export async function listTeacherInvites(orgId: string): Promise<OrganizationInvite[]> {
  return fetchJson<OrganizationInvite[]>(`/api/organizations/${orgId}/invites`, {
    method: "GET",
  });
}

/**
 * Org admin: invite a teacher straight into this school.
 *
 * They arrive approved — the person issuing the link is the person who would
 * otherwise approve the request, so there is nothing left to wait for.
 */
export async function inviteTeacher(
  orgId: string,
  email: string,
): Promise<OrganizationInvite> {
  return fetchJson<OrganizationInvite>(`/api/organizations/${orgId}/invites`, {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

/** Superadmin: set (or clear, with 0) a school's monthly token allowance. */
export async function setMonthlyTokenLimit(
  orgId: string,
  monthlyTokenLimit: number,
): Promise<OrganizationDetail> {
  return fetchJson<OrganizationDetail>(`/api/organizations/${orgId}`, {
    method: "PATCH",
    body: JSON.stringify({ monthly_token_limit: monthlyTokenLimit }),
  });
}

/**
 * Rupees, as an Indian reader expects them: ₹1,84,000 rather than ₹184,000.
 *
 * Whole rupees above ₹100 — paise on a four-figure platform bill are noise in
 * a column you are scanning for magnitude. Every surface that renders this owes
 * the reader the word "estimated" somewhere nearby: our token counts cannot see
 * cached-input discounts or the separate image-token tiers, so this will not
 * reconcile against an invoice to the paisa.
 */
export function formatInr(amount: number): string {
  const value = Number(amount) || 0;
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: value >= 100 ? 0 : 2,
  }).format(value);
}

/**
 * Which school this account is currently working as, and what else it could be.
 *
 * A teacher with two memberships is at any moment working as one of them: one
 * masthead on the paper, one budget the tokens come out of, one set of
 * colleagues in the admin screens.
 */
export type MembershipChoice = {
  organization_id: string;
  organization_name: string;
  role: "org_admin" | "teacher";
  status: "pending" | "approved" | "rejected";
  is_active: boolean;
};

export async function listMyMemberships(): Promise<{
  active_organization_id: string | null;
  memberships: MembershipChoice[];
}> {
  return fetchJson("/api/organizations/switch", { method: "GET" });
}

/**
 * Switch which school is in effect.
 *
 * Nothing is moved, copied or re-scoped — papers stay with the account that
 * made them. What changes is the school the next paper is branded and billed
 * as, and whose admin screens you see.
 */
export async function switchOrganization(organizationId: string): Promise<void> {
  await fetchJson("/api/organizations/switch", {
    method: "POST",
    body: JSON.stringify({ organization_id: organizationId }),
  });
}
