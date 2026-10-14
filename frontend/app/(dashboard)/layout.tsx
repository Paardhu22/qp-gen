"use client";

import { TopNavbar } from "@/components/layout/top-navbar";
import { ProtectedLayout } from "@/components/layout/protected-layout";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ProtectedLayout>
      <div className="h-dvh relative bg-background overflow-hidden flex flex-col">
        <TopNavbar />
        <main className="min-h-0 flex-1 overflow-auto overflow-x-hidden flex flex-col pb-safe">
          {children}
        </main>
      </div>
    </ProtectedLayout>
  );
}
