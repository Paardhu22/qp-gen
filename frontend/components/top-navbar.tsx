"use client";

import { useSession } from "@/lib/auth-client";
import Link from "next/link";

export const TopNavbar = () => {
  const { data: session } = useSession();

  return (
    <div className="flex items-center p-4 border-b border-zinc-800 bg-zinc-950/50 backdrop-blur-md">
      <div className="flex w-full justify-end">
        <div className="flex items-center gap-x-4">
          <div className="flex flex-col text-right hidden md:block">
            <span className="text-sm font-medium text-white">{session?.user?.name || "User"}</span>
            <span className="text-xs text-zinc-400">{session?.user?.email || ""}</span>
          </div>
          <Link
            href="/profile"
            className="h-8 w-8 rounded-full bg-indigo-600 flex items-center justify-center text-sm font-bold text-white hover:bg-indigo-500 transition"
            aria-label="Open profile"
          >
            {session?.user?.name?.charAt(0).toUpperCase() || "U"}
          </Link>
        </div>
      </div>
    </div>
  );
};
