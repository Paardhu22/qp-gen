import { AuthThemeScope } from "@/components/auth-theme-scope";

const FORCE_LIGHT_SCRIPT = `
(function () {
  try {
    var h = document.documentElement;
    var wasDark = h.classList.contains("dark");
    if (wasDark) {
      h.classList.remove("dark");
      h.setAttribute("data-prev-theme", "dark");
    }
    h.setAttribute("data-auth-page", "");
  } catch (e) {}
})();
`;

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <script dangerouslySetInnerHTML={{ __html: FORCE_LIGHT_SCRIPT }} />
      <AuthThemeScope>{children}</AuthThemeScope>
    </>
  );
}
