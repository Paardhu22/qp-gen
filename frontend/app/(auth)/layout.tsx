import type { Metadata } from "next";

import { AuthThemeScope } from "@/components/auth-theme-scope";

// Login/register/reset pages carry the homepage title, so keep them out of search results.
export const metadata: Metadata = { robots: { index: false, follow: true } };

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <AuthThemeScope>{children}</AuthThemeScope>
    </>
  );
}
