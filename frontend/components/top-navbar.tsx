"use client";

import { useEffect, useState } from "react";
import { useSession, signOut, isSuperAdmin, isOrgAdmin } from "@/lib/auth-client";
import { SchoolSwitcher } from "@/components/school-switcher";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  ListChecks,
  FileText,
  BookOpen,
  LayoutTemplate,
  Settings,
  ShieldCheck,
  LogOut,
  Menu,
  X,
} from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Dialog as Drawer } from "@base-ui/react/dialog";
import Image from "next/image";
import Link from "next/link";
import { cn } from "@/lib/utils";

const navItems = [
  { icon: LayoutDashboard, label: "Dashboard", href: "/dashboard" },
  { icon: ListChecks, label: "Question Bank", href: "/questions" },
  { icon: FileText, label: "Editor", href: "/editor" },
  { icon: BookOpen, label: "Papers", href: "/papers" },
  { icon: LayoutTemplate, label: "Templates", href: "/templates" },
  { icon: Settings, label: "Settings", href: "/settings" },
];

export const TopNavbar = () => {
  const { data: session, refresh: refreshSession } = useSession();
  const pathname = usePathname();
  const router = useRouter();
  const [drawerOpen, setDrawerOpen] = useState(false);

  const user = session?.user;
  const items = isSuperAdmin(user) || isOrgAdmin(user)
    ? [...navItems, { icon: ShieldCheck, label: "Admin", href: "/admin" }]
    : navItems;

  const handleSignOut = async () => {
    await signOut({
      fetchOptions: {
        onSuccess: () => router.push("/login"),
      },
    });
  };

  // Close the mobile drawer whenever the route changes.
  useEffect(() => {
    setDrawerOpen(false);
  }, [pathname]);

  // A navigation drawer should not survive a resize to the desktop layout.
  useEffect(() => {
    const desktop = window.matchMedia("(min-width: 1024px)");
    const closeOnDesktop = () => { if (desktop.matches) setDrawerOpen(false); };
    desktop.addEventListener("change", closeOnDesktop);
    return () => desktop.removeEventListener("change", closeOnDesktop);
  }, []);

  const userName = session?.user?.name || "User";
  const userEmail = session?.user?.email || "";
  const userInitial = userName.charAt(0).toUpperCase();

  return (
    <Drawer.Root open={drawerOpen} onOpenChange={setDrawerOpen}>
    <header className="shrink-0 border-b border-border bg-background pt-safe px-safe sticky top-0 z-40">
      <div className="flex items-center px-4 sm:px-6 h-16 lg:h-[4.5rem]">
        <div className="flex w-full justify-between items-center h-full gap-2">
          {/* Logo */}
          <Link href="/dashboard" aria-label="HSAT home" className="flex items-center h-full shrink-0 lg:w-[calc(16rem-1.5rem)]">
            <div className="relative h-11 w-28 sm:h-12 sm:w-36">
              <Image
                src="/lighttheme.png"
                alt="HSAT"
                fill
                sizes="(max-width: 640px) 112px, 144px"
                className="dark:hidden object-contain object-left"
                priority
              />
              <Image
                src="/darktheme.svg"
                alt="HSAT"
                fill
                className="hidden dark:block object-contain object-left"
                priority
              />
            </div>
          </Link>

          {/* Desktop nav links (lg and up) */}
          <nav className="hidden lg:flex items-center gap-1">
            {items.map(({ icon: Icon, label, href }) => {
              const active = pathname.startsWith(href);
              return (
                <Link
                  key={href}
                  href={href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex items-center justify-center gap-1.5 rounded-full px-3 py-2 text-xs font-medium transition-colors duration-150 select-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
                    active
                      ? "bg-primary/10 text-primary font-semibold"
                      : "text-muted-foreground hover:text-foreground hover:bg-accent",
                  )}
                >
                  {Icon && <Icon className="h-4 w-4" strokeWidth={1.7} />}
                  <span>{label}</span>
                </Link>
              );
            })}
          </nav>

          {/* Right side */}
          <div className="flex items-center gap-x-2 sm:gap-x-3 shrink-0">
            {/* User dropdown (shown on lg+ where there's room beside the nav) */}
            <div className="hidden lg:block">
              <DropdownMenu>
                <DropdownMenuTrigger aria-label="Open account menu" className="flex items-center gap-2 rounded-full outline-none focus-visible:ring-2 focus-visible:ring-ring cursor-pointer">
                  <span className="max-w-32 truncate text-xs font-medium text-muted-foreground hidden xl:block">
                    {userName}
                  </span>
                  <div className="h-8 w-8 rounded-full border border-border bg-muted flex items-center justify-center text-xs font-medium text-muted-foreground hover:bg-accent transition-colors">
                    {userInitial}
                  </div>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-48">
                  <div className="px-2 py-1.5 flex flex-col gap-0.5">
                    <span className="font-semibold text-sm text-foreground">
                      {userName}
                    </span>
                    <span className="text-xs text-muted-foreground truncate">
                      {userEmail}
                    </span>
                  </div>
                  {/* Renders nothing for the one-school accounts that are the
                      overwhelming majority. */}
                  <SchoolSwitcher user={user} onSwitched={refreshSession} />
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

            {/* Mobile/tablet: avatar (visual only) + hamburger */}
            <div className="lg:hidden h-9 w-9 rounded-full border border-border bg-muted flex items-center justify-center text-xs font-medium text-muted-foreground">
              {userInitial}
            </div>
            <Drawer.Trigger
              aria-label="Open navigation menu"
              aria-expanded={drawerOpen}
              className="lg:hidden inline-flex items-center justify-center h-11 w-11 -mr-1 rounded-lg text-foreground hover:bg-accent transition-colors"
            >
              <Menu className="h-6 w-6" />
            </Drawer.Trigger>
          </div>
        </div>
      </div>

    </header>

      {/* The primitive handles focus trapping, Escape, and restoring focus. */}
      <Drawer.Portal>
            <Drawer.Backdrop className="fixed inset-0 z-50 bg-black/35 transition-opacity duration-150 data-starting-style:opacity-0 data-ending-style:opacity-0 motion-reduce:transition-none" />
            <Drawer.Popup
              className="fixed right-0 top-0 z-50 h-dvh w-[min(20rem,90vw)] bg-sidebar border-l border-border flex flex-col pt-safe pb-safe pr-safe outline-none transition-transform duration-200 ease-[var(--ease)] data-starting-style:translate-x-full data-ending-style:translate-x-full motion-reduce:transition-none"
            >
              <Drawer.Title className="sr-only">Navigation menu</Drawer.Title>
              {/* Drawer header: user + close */}
              <div className="flex items-center justify-between gap-3 px-4 h-16 border-b border-border">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="h-10 w-10 shrink-0 rounded-full bg-primary flex items-center justify-center text-base font-bold text-primary-foreground">
                    {userInitial}
                  </div>
                  <div className="flex flex-col min-w-0">
                    <span className="font-semibold text-sm text-foreground truncate">
                      {userName}
                    </span>
                    <span className="text-xs text-muted-foreground truncate">
                      {userEmail}
                    </span>
                  </div>
                </div>
                <Drawer.Close
                  aria-label="Close navigation menu"
                  className="inline-flex items-center justify-center h-11 w-11 -mr-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
                >
                  <X className="h-6 w-6" />
                </Drawer.Close>
              </div>

              {/* Drawer nav */}
              <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
                {items.map(({ icon: Icon, label, href }) => {
                  const active = pathname.startsWith(href);
                  return (
                    <Link
                      key={href}
                      href={href}
                      aria-current={active ? "page" : undefined}
                      onClick={() => setDrawerOpen(false)}
                      className={cn(
                        "flex items-center gap-3 px-3 py-3 rounded-lg text-sm font-medium transition-colors",
                        active
                          ? "bg-primary/10 text-primary font-semibold"
                          : "text-muted-foreground hover:text-foreground hover:bg-accent",
                      )}
                    >
                      {Icon && <Icon className="h-5 w-5 shrink-0" />}
                      <span>{label}</span>
                    </Link>
                  );
                })}
              </nav>

              {/* Drawer footer: school switcher (multi-school accounts only)
                  then logout */}
              <SchoolSwitcher
                user={user}
                onSwitched={refreshSession}
                className="border-t border-border px-3 py-3"
              />
              <div className="px-3 py-3 border-t border-border">
                <button
                  type="button"
                  onClick={handleSignOut}
                  className="flex w-full items-center gap-3 px-3 py-3 rounded-lg text-sm font-medium text-destructive hover:bg-destructive/10 transition-colors"
                >
                  <LogOut className="h-5 w-5 shrink-0" />
                  Log out
                </button>
              </div>
            </Drawer.Popup>
      </Drawer.Portal>
    </Drawer.Root>
  );
};
