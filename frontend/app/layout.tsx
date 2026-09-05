import type { Metadata, Viewport } from "next";
import "./globals.css";
import "../styles/editor.css";
import "../styles/press-check.css";
import "../styles/grainient.css";
import "katex/dist/katex.min.css";
import { Providers } from "@/components/providers";
import { Toaster } from "sonner";
import { Inter, Playfair_Display, Sora } from "next/font/google";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

const sora = Sora({
  subsets: ["latin"],
  variable: "--font-sora",
  weight: ["400", "500", "600", "700"],
});

// The display face, for page identity only -- the landing title and the <h1>
// of each page. Component chrome (card titles, dialog titles) stays on Inter
// via `--font-heading`; a high-contrast serif at 14px inside a dialog reads as
// a mistake rather than as brand.
//
// Playfair over the other candidates because it ships a variable weight axis.
// PageTitle is `font-semibold`, and a face with only a 400 cut would have that
// synthesised by the browser -- a smeared fake bold, which on a high-contrast
// serif is exactly where the fake is most obvious.
const playfair = Playfair_Display({
  subsets: ["latin"],
  variable: "--font-playfair",
  // The weights the app actually asks for. Loading the whole axis would ship
  // range nothing uses.
  weight: ["500", "600", "700"],
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
      className={`${inter.variable} ${playfair.variable} ${sora.variable}`}
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
