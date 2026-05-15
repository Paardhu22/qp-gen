"use client";

import { useSession } from "@/lib/auth-client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function ProfilePage() {
  const { data: session, isLoading } = useSession();
  const user = session?.user;

  return (
    <div className="p-8 space-y-6">
      <div>
        <h2 className="text-3xl font-bold tracking-tight text-white">Profile</h2>
        <p className="text-zinc-400 mt-2">Your account details.</p>
      </div>

      <Card className="bg-zinc-950 border-zinc-800">
        <CardHeader>
          <CardTitle className="text-zinc-100">Basic Details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {isLoading ? (
            <div className="text-zinc-500">Loading profile...</div>
          ) : (
            <div className="space-y-3 text-sm">
              <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
                <span className="text-zinc-400">Name</span>
                <span className="text-zinc-100">{user?.name || "-"}</span>
              </div>
              <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
                <span className="text-zinc-400">Email</span>
                <span className="text-zinc-100">{user?.email || "-"}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-zinc-400">Email verified</span>
                <span className="text-zinc-100">{user?.email_verified ? "Yes" : "No"}</span>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
