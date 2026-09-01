import { Suspense } from "react";

import { Spinner } from "@/components/ui/spinner";
import { OnboardOrganizationForm } from "@/components/onboard-organization-form";

export default function OnboardPage() {
  // Next.js 16 requires a Suspense boundary around any component that calls
  // useSearchParams() in a statically-prerendered route.
  return (
    <Suspense fallback={
        <div className="flex min-h-svh items-center justify-center">
          <Spinner size="page" />
        </div>
      }>
      <OnboardOrganizationForm />
    </Suspense>
  );
}
