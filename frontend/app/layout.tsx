import type { Metadata, Viewport } from "next";
import "./globals.css";
import "../styles/editor.css";
import "../styles/press-check.css";
import "../styles/grainient.css";
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
        <Toaster 
          position="top-right" 
          theme="system" 
          toastOptions={{
            classNames: {
              toast: "bg-background text-foreground border-border shadow-lg",
              description: "text-muted-foreground",
              actionButton: "bg-primary text-primary-foreground",
              cancelButton: "bg-muted text-muted-foreground",
            },
          }} 
        />
      </body>
    </html>
  );
}
