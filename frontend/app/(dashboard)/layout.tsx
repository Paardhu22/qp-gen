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
      <div className="h-screen relative bg-background overflow-hidden flex flex-col">
        <TopNavbar />
        <main className="flex-1 overflow-auto flex flex-col">
          {children}
        </main>
      </div>
    </ProtectedLayout>
  );
}
