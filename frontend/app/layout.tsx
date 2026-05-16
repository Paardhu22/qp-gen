import type { Metadata } from "next";
import "./globals.css";
import "katex/dist/katex.min.css";
import { Providers } from "@/components/providers";
import { Toaster } from "sonner";

export const metadata: Metadata = {
  title: "Paper Gen - AI Question Paper Generator",
  description: "AI-powered Question Paper Generator SaaS",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="bg-background text-foreground">
        <Providers>
          {children}
          <Toaster position="top-right" richColors theme="system" />
        </Providers>
      </body>
    </html>
  );
}
