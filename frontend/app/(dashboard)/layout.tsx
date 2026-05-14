"use client";

import { Sidebar } from "@/components/sidebar";
import { TopNavbar } from "@/components/top-navbar";
import { ProtectedLayout } from "@/components/protected-layout";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ProtectedLayout>
      <div className="h-screen relative bg-zinc-900 overflow-hidden flex">
        <div className="hidden h-full md:flex md:w-72 md:flex-col md:fixed md:inset-y-0 z-[80]">
          <Sidebar />
        </div>
        <main className="md:pl-72 flex-1 flex flex-col">
          <TopNavbar />
          <div className="flex-1 overflow-auto">
            {children}
          </div>
        </main>
      </div>
    </ProtectedLayout>
  );
}
