import { AuthThemeScope } from "@/components/auth-theme-scope";

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
