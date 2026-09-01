import { Suspense } from "react";

import { Spinner } from "@/components/ui/spinner";
import { ResetPasswordForm } from "@/components/reset-password-form";

export default function ResetPasswordPage() {
  // Next.js 16 requires a Suspense boundary around any component that
  // calls `useSearchParams()` in a statically-prerendered route, so the
  // server can render a fallback for the synchronous shell while the
  // search-params hook waits for client hydration.
  return (
    <Suspense fallback={
        <div className="flex min-h-svh items-center justify-center">
          <Spinner size="page" />
        </div>
      }>
      <ResetPasswordForm />
    </Suspense>
  );
}
