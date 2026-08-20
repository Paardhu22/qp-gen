"use client";

/**
 * The email domains a school claims.
 *
 * Small, but it is what turns signup from "find your school among all of
 * them" into "confirm this is your school" — and picking the wrong one there
 * is the most common way a teacher ends up stranded in a pending queue that
 * nobody at that school will action.
 *
 * A hint and nothing more: a matched domain pre-selects the school, and the
 * membership still starts pending. Domains are trivially spoofable at signup,
 * so the only thing this may safely do is reorder a list that was already
 * public. The one place a domain grants something is a teacher invite, and
 * that is granted by the admin who issued the link, not by the domain.
 */

import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { AtSign } from "lucide-react";
import { updateOrganization, type OrganizationDetail } from "@/lib/organizations-client";

export function SchoolDomains({
  org,
  onSaved,
}: {
  org: OrganizationDetail;
  onSaved: (org: OrganizationDetail) => void;
}) {
  const [value, setValue] = useState(org.email_domains.join(", "));
  const [saving, setSaving] = useState(false);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const updated = await updateOrganization(org.id, { email_domains: value });
      // Re-read from the response rather than keeping what was typed: the
      // backend normalises ("@School.EDU" → "school.edu"), and showing the raw
      // input back would suggest it was stored as typed.
      setValue(updated.email_domains.join(", "));
      onSaved(updated);
      toast.success(
        updated.email_domains.length === 0
          ? "Domain matching is off for this school"
          : "Saved. Teachers at that domain will see this school pre-selected.",
      );
    } catch (err: any) {
      toast.error(err?.message || "Could not save those domains");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <AtSign className="h-4 w-4 text-muted-foreground" aria-hidden />
          Staff email domain
        </CardTitle>
        <CardDescription>
          Teachers signing up with an address here see this school pre-selected.
          They still need approving — this only saves them finding you in a list.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSave} className="space-y-2">
          <div className="flex flex-col gap-2 sm:flex-row">
            <Input
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="yourschool.edu.in"
              aria-label="Staff email domains, comma separated"
            />
            <Button type="submit" disabled={saving} className="shrink-0">
              {saving ? "Saving…" : "Save"}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Separate several with commas. Public providers like gmail.com can&apos;t
            be used — they would match everybody.
          </p>
        </form>
      </CardContent>
    </Card>
  );
}
