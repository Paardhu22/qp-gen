import { Suspense } from "react";
import { RegisterForm } from "@/components/register-form";

export default function RegisterPage() {
  // The form reads `?invite=` via useSearchParams(), which Next.js 16 requires
  // a Suspense boundary around in a statically-prerendered route — same reason
  // as /onboard.
  return (
    <Suspense fallback={<div className="flex min-h-svh items-center justify-center" />}>
      <RegisterForm />
    </Suspense>
  );
}
