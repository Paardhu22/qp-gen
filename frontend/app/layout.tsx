import type { Metadata, Viewport } from "next";
import "./globals.css";
import "../styles/editor.css";
import "../styles/press-check.css";
import "../styles/grainient.css";
import "katex/dist/katex.min.css";
import { Providers } from "@/components/providers";
import { Toaster } from "sonner";
import localFont from "next/font/local";
import { SITE_DESCRIPTION, SITE_NAME, SITE_URL } from "@/lib/site";

const manrope = localFont({
  src: "../assets/fonts/manrope.ttf",
  variable: "--font-manrope",
  weight: "200 800",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: `${SITE_NAME} - Question Paper Generator | HSAT Edu Solutions`, template: `%s | ${SITE_NAME}` },
  description: SITE_DESCRIPTION,
  applicationName: SITE_NAME,
  keywords: ["HSAT", "HSAT Edu Solutions", "QP-Gen", "qp gen", "question paper generator", "question bank", "exam paper maker"],
  alternates: { canonical: "/" },
  openGraph: {
    type: "website",
    siteName: SITE_NAME,
    title: `${SITE_NAME} - Question Paper Generator`,
    description: SITE_DESCRIPTION,
    url: SITE_URL,
    images: [{ url: "/IMG-20260514-WA0000.jpg-removebg-preview.png", width: 797, height: 313, alt: "HSAT Edu Solutions" }],
  },
  twitter: { card: "summary", title: `${SITE_NAME} - Question Paper Generator`, description: SITE_DESCRIPTION },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fcfcfd" },
    { media: "(prefers-color-scheme: dark)", color: "#181b24" },
  ],
};

const jsonLd = {
  "@context": "https://schema.org",
  "@graph": [
    { "@type": "Organization", name: "HSAT Edu Solutions", alternateName: ["HSAT", "HSAT Edu"], url: SITE_URL, logo: `${SITE_URL}/icon.png` },
    { "@type": "WebSite", name: SITE_NAME, alternateName: ["QP-Gen", "QP Gen", "HSAT"], url: SITE_URL },
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
      className={manrope.variable}
    >
      <body className="font-sans bg-background text-foreground">
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
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
