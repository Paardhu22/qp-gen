import { notFound } from "next/navigation";

/**
 * Browser harnesses for headless checks (pagination, exports). They sit
 * outside the auth guard on purpose, so a production build hides them unless
 * it is started with ENABLE_TEST_HARNESS=1 for a test run. Dynamic so the
 * flag is read when the server starts, not baked in at build time.
 */
export const dynamic = "force-dynamic";

export default function HarnessLayout({ children }: { children: React.ReactNode }) {
  if (process.env.NODE_ENV === "production" && process.env.ENABLE_TEST_HARNESS !== "1") notFound();
  return children;
}
