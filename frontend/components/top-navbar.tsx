"use client";

import { useEffect, useState } from "react";
import { useSession, signOut } from "@/lib/auth-client";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  ListChecks,
  FileText,
  BookOpen,
  Settings,
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
import { AnimatePresence, motion } from "framer-motion";
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
  const [drawerOpen, setDrawerOpen] = useState(false);

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

  // Lock background scroll + allow Escape-to-close while the drawer is open.
  useEffect(() => {
    if (!drawerOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setDrawerOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKey);
    };
  }, [drawerOpen]);

  const userName = session?.user?.name || "User";
  const userEmail = session?.user?.email || "";
  const userInitial = userName.charAt(0).toUpperCase();

  return (
    <header className="border-b border-border bg-background/80 backdrop-blur-md pt-safe px-safe sticky top-0 z-40">
      <div className="flex items-center px-3 sm:px-4 h-16 lg:h-[4.5rem]">
        <div className="flex w-full justify-between items-center h-full gap-2">
          {/* Logo */}
          <Link href="/dashboard" className="flex items-center h-full shrink-0">
            <div className="relative h-11 w-32 sm:h-14 sm:w-44">
              <Image
                src="/lighttheme.png"
                alt="Logo"
                fill
                sizes="(max-width: 768px) 128px, 200px"
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

          {/* Desktop nav links (lg and up) */}
          <nav className="hidden lg:flex items-center gap-1">
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
          <div className="flex items-center gap-x-2 sm:gap-x-3 shrink-0">
            {/* User dropdown (shown on lg+ where there's room beside the nav) */}
            <div className="hidden lg:block">
              <DropdownMenu>
                <DropdownMenuTrigger className="flex items-center gap-2 rounded-full outline-none focus-visible:ring-2 focus-visible:ring-ring cursor-pointer">
                  <span className="text-sm font-medium text-foreground hidden md:block">
                    {userName}
                  </span>
                  <div className="h-8 w-8 rounded-full bg-primary flex items-center justify-center text-sm font-bold text-primary-foreground hover:opacity-80 transition-opacity">
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
            <div className="lg:hidden h-9 w-9 rounded-full bg-primary flex items-center justify-center text-sm font-bold text-primary-foreground">
              {userInitial}
            </div>
            <button
              type="button"
              onClick={() => setDrawerOpen(true)}
              aria-label="Open navigation menu"
              aria-expanded={drawerOpen}
              className="lg:hidden inline-flex items-center justify-center h-11 w-11 -mr-1 rounded-lg text-foreground hover:bg-accent transition-colors"
            >
              <Menu className="h-6 w-6" />
            </button>
          </div>
        </div>
      </div>

      {/* Mobile slide-out drawer */}
      <AnimatePresence>
        {drawerOpen && (
          <motion.div
            className="fixed inset-0 z-50 lg:hidden"
            initial="closed"
            animate="open"
            exit="closed"
          >
            {/* Backdrop */}
            <motion.div
              className="absolute inset-0 bg-black/40 backdrop-blur-sm"
              variants={{ open: { opacity: 1 }, closed: { opacity: 0 } }}
              transition={{ duration: 0.2 }}
              onClick={() => setDrawerOpen(false)}
              aria-hidden="true"
            />

            {/* Panel */}
            <motion.div
              role="dialog"
              aria-modal="true"
              aria-label="Navigation menu"
              className="absolute right-0 top-0 h-full w-[82%] max-w-xs bg-background border-l border-border shadow-xl flex flex-col pt-safe pb-safe pr-safe"
              variants={{
                open: { x: 0 },
                closed: { x: "100%" },
              }}
              transition={{ type: "tween", duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
            >
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
                <button
                  type="button"
                  onClick={() => setDrawerOpen(false)}
                  aria-label="Close navigation menu"
                  className="inline-flex items-center justify-center h-11 w-11 -mr-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
                >
                  <X className="h-6 w-6" />
                </button>
              </div>

              {/* Drawer nav */}
              <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
                {navItems.map(({ icon: Icon, label, href }) => {
                  const active = pathname.startsWith(href);
                  return (
                    <Link
                      key={href}
                      href={href}
                      onClick={() => setDrawerOpen(false)}
                      className={cn(
                        "flex items-center gap-3 px-3 py-3 rounded-lg text-sm font-medium transition-colors",
                        active
                          ? "bg-foreground text-background"
                          : "text-muted-foreground hover:text-foreground hover:bg-accent",
                      )}
                    >
                      {Icon && <Icon className="h-5 w-5 shrink-0" />}
                      <span>{label}</span>
                    </Link>
                  );
                })}
              </nav>

              {/* Drawer footer: logout */}
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
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  );
};
