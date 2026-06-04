"use client";

import { useSession, signOut } from "@/lib/auth-client";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  ListChecks,
  FileText,
  BookOpen,
  Settings,
  LogOut,
} from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import Image from "next/image";
import Link from "next/link";
import { cn } from "@/lib/utils";

const navItems = [
  { icon: LayoutDashboard, label: "Dashboard", href: "/dashboard" },
  { icon: ListChecks, label: "Saved Questions", href: "/paper-library" },
  { icon: FileText, label: "Editor", href: "/editor" },
  { icon: BookOpen, label: "Question Paper", href: "/question-bank" },
  { icon: Settings, label: "Settings", href: "/settings" },
];

export const TopNavbar = () => {
  const { data: session } = useSession();
  const pathname = usePathname();
  const router = useRouter();

  const handleSignOut = async () => {
    await signOut({
      fetchOptions: {
        onSuccess: () => router.push("/login"),
      },
    });
  };

  return (
    <div className="flex items-center px-4 border-b border-border bg-background/50 backdrop-blur-md h-[4.5rem]">
      <div className="flex w-full justify-between items-center h-full">
        {/* Logo */}
        <Link href="/dashboard" className="flex items-center h-full">
          <div className="relative h-14 w-44">
            <Image
              src="/lighttheme.png"
              alt="Logo"
              fill
              sizes="(max-width: 768px) 100vw, 200px"
              className="dark:hidden object-contain object-left"
              priority
            />
            <Image
              src="/darktheme.svg"
              alt="Logo"
              fill
              className="hidden dark:block object-contain object-left"
              priority
            />
          </div>
        </Link>

        {/* Nav links */}
        <nav className="flex items-center gap-1">
          {navItems.map(({ icon: Icon, label, href }) => {
            const active = pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex flex-col items-center justify-center gap-0.5 px-4 py-1.5 rounded-lg text-xs font-medium transition-colors select-none",
                  active
                    ? "bg-foreground text-background"
                    : "text-muted-foreground hover:text-foreground hover:bg-accent",
                )}
              >
                {Icon && <Icon className="h-4 w-4" />}
                <span>{label}</span>
              </Link>
            );
          })}
        </nav>

        {/* Right side */}
        <div className="flex items-center gap-x-3">
          <DropdownMenu>
            <DropdownMenuTrigger className="flex items-center gap-2 rounded-full outline-none focus-visible:ring-2 focus-visible:ring-ring cursor-pointer">
              <span className="text-sm font-medium text-foreground hidden md:block">
                {session?.user?.name || "User"}
              </span>
              <div className="h-8 w-8 rounded-full bg-primary flex items-center justify-center text-sm font-bold text-primary-foreground hover:opacity-80 transition-opacity">
                {session?.user?.name?.charAt(0).toUpperCase() || "U"}
              </div>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
              <div className="px-2 py-1.5 flex flex-col gap-0.5">
                <span className="font-semibold text-sm text-foreground">
                  {session?.user?.name || "User"}
                </span>
                <span className="text-xs text-muted-foreground truncate">
                  {session?.user?.email || ""}
                </span>
              </div>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={handleSignOut}
                className="text-destructive focus:text-destructive focus:bg-destructive/10 cursor-pointer gap-2"
              >
                <LogOut className="h-4 w-4" />
                Log out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </div>
  );
};
