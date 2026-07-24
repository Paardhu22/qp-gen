import type { Metadata, Viewport } from "next";
import "./globals.css";
import "../styles/editor.css";
import "katex/dist/katex.min.css";
import { Providers } from "@/components/providers";
import { Toaster } from "sonner";
import { Inter } from "next/font/google";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "Paper Gen -  Paper Generator",
  description: "Paper Generator SaaS",
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
      className={`${inter.variable}`}
    >
      <body className="font-sans bg-background text-foreground">
        <Providers>{children}</Providers>
        <Toaster position="top-right" richColors theme="system" />
      </body>
    </html>
  );
}
