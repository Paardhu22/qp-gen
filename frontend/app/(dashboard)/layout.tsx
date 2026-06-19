"use client";

import { TopNavbar } from "@/components/top-navbar";
import { ProtectedLayout } from "@/components/protected-layout";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ProtectedLayout>
      <div className="h-dvh relative bg-background overflow-hidden flex flex-col">
        <TopNavbar />
        <main className="flex-1 overflow-auto overflow-x-hidden flex flex-col pb-safe">
          {children}
        </main>
      </div>
    </ProtectedLayout>
  );
}
