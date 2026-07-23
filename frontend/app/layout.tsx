import type { Metadata, Viewport } from "next";
import "./globals.css";
import "katex/dist/katex.min.css";
import { Providers } from "@/components/providers";
import { Toaster } from "sonner";
import { Geist, Geist_Mono } from "next/font/google";

// Registered as CSS variables (not just `.className`) so the Tailwind
// `--font-sans` / `--font-mono` / `--font-heading` tokens in globals.css
// resolve to a real font instead of the browser default. See globals.css
// `@theme inline`.
const geistSans = Geist({
  subsets: ["latin"],
  variable: "--font-geist-sans",
});

const geistMono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-geist-mono",
});

export const metadata: Metadata = {
  title: "Paper Gen -  Question Paper Generator",
  description: "Question Paper Generator SaaS",
};

// `viewport-fit=cover` lets the app paint into the iOS/Android safe areas so our
// `env(safe-area-inset-*)` padding can reclaim them. We deliberately allow zoom
// (no maximumScale / userScalable lock) to keep pinch-zoom accessibility.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#0a0a0a" },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable}`}
    >
      <body className="font-sans bg-background text-foreground">
        <Providers>{children}</Providers>
        <Toaster position="top-right" richColors theme="system" />
      </body>
    </html>
  );
}
