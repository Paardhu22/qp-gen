"use client";

import { useSession } from "@/lib/auth-client";
import { ThemeToggle } from "./ui/curtain-theme-toggle";
import { usePathname, useRouter } from "next/navigation";
import GooeyNav from "./GooeyNav";
import { LayoutDashboard, FolderOpen, FileText, History, Settings } from "lucide-react";
import Image from "next/image";
import Link from "next/link";

const navItems = [
  { icon: <LayoutDashboard className="h-5 w-5" />, href: "/dashboard" },
  { icon: <FolderOpen className="h-5 w-5" />, href: "/saved" },
  { icon: <FileText className="h-5 w-5" />, href: "/editor" },
  { icon: <History className="h-5 w-5" />, href: "/history" },
  { icon: <Settings className="h-5 w-5" />, href: "/settings" },
];

export const TopNavbar = () => {
  const { data: session } = useSession();
  const pathname = usePathname();
  const router = useRouter();

  const activeIndex = navItems.findIndex((item) => pathname.startsWith(item.href));

  return (
    <div className="flex items-center p-4 border-b border-border bg-background/50 backdrop-blur-md h-[4.5rem]">
      <div className="flex w-full justify-between items-center h-full">
        <div className="flex items-center">
          <Link href="/dashboard" className="flex items-center h-full">
            <div className="relative h-14 w-44">
              <Image
                src="/lighttheme.png"
                alt="Logo"
                fill
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
        </div>
        <div className="flex items-center gap-x-4 h-full">
          <div className="h-full flex items-center mr-4">
            <GooeyNav
              items={navItems}
              initialActiveIndex={activeIndex >= 0 ? activeIndex : 0}
              onNavigate={(href) => router.push(href)}
              animationTime={600}
              particleCount={10}
            />
          </div>
          <ThemeToggle variant="icon" />
          <div className="flex flex-col text-right hidden md:block">
            <span className="text-sm font-medium text-foreground">{session?.user?.name || "User"}</span>
          </div>
          <div className="h-8 w-8 rounded-full bg-primary flex items-center justify-center text-sm font-bold text-primary-foreground">
            {session?.user?.name?.charAt(0).toUpperCase() || "U"}
          </div>
        </div>
      </div>
      <svg xmlns="http://www.w3.org/2000/svg" version="1.1" className="hidden">
        <defs>
          <filter id="goo">
            <feGaussianBlur in="SourceGraphic" stdDeviation="10" result="blur" />
            <feColorMatrix in="blur" mode="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 18 -7" result="goo" />
            <feComposite in="SourceGraphic" in2="goo" operator="atop"/>
          </filter>
        </defs>
      </svg>
    </div>
  );
};
