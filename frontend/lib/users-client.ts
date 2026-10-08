import { fetchJson } from "@/lib/api-client";

/**
 * A user as the platform admin table sees them — the account, plus which
 * school they belong to and in what role.
 *
 * `membership` is null for two very different people: someone who signed up
 * and has not picked a school yet, and the superadmin, who deliberately
 * belongs to none. The table has to distinguish them, so it reads
 * `is_superadmin` rather than inferring anything from the missing membership.
 */
export type PlatformUser = {
  id: string;
  name: string;
  email: string;
  image: string | null;
  status: "pending" | "approved" | "admin" | "rejected";
  is_superadmin: boolean;
  tokens_consumed: number;
  membership: {
    organization_id: string;
    organization_name: string;
    role: "org_admin" | "teacher";
    status: "pending" | "approved" | "rejected";
  } | null;
};

export type PlatformUserPage = {
  total: number;
  limit: number;
  offset: number;
  users: PlatformUser[];
};

/**
 * Platform admin / superadmin: every user on the account.
 *
 * `q` filters on name or email and `status` on the account status, both server
 * side — filtering the current page in the browser would silently hide matches
 * that live on the next one.
 */
export async function listPlatformUsers(params?: {
  q?: string;
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<PlatformUserPage> {
  const search = new URLSearchParams();
  if (params?.q) search.set("q", params.q);
  if (params?.status) search.set("status", params.status);
  search.set("limit", String(params?.limit ?? 50));
  search.set("offset", String(params?.offset ?? 0));
  // `/api/auth/`, not `/api/accounts/` — apps.accounts.urls is mounted under
  // the auth prefix in config/urls.py.
  return fetchJson<PlatformUserPage>(`/api/auth/users?${search.toString()}`, {
    method: "GET",
  });
}
