"use client";

import { useSession } from "@/lib/auth-client";
import { ThemeToggle } from "./ui/curtain-theme-toggle";

export const TopNavbar = () => {
  const { data: session } = useSession();

  return (
    <div className="flex items-center p-4 border-b border-border bg-background/50 backdrop-blur-md">
      <div className="flex w-full justify-between items-center">
        <div>
          {/* Add any left side content if needed */}
        </div>
        <div className="flex items-center gap-x-4">
          <ThemeToggle variant="icon" />
          <div className="flex flex-col text-right hidden md:block">
            <span className="text-sm font-medium text-foreground">{session?.user?.name || "User"}</span>
            <span className="text-xs text-muted-foreground">{session?.user?.email || ""}</span>
          </div>
          <div className="h-8 w-8 rounded-full bg-primary flex items-center justify-center text-sm font-bold text-primary-foreground">
            {session?.user?.name?.charAt(0).toUpperCase() || "U"}
          </div>
        </div>
      </div>
    </div>
  );
};
