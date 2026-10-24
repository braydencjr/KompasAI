import type { Metadata } from "next";
import { Geist, Geist_Mono, Newsreader } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "./components/Auth";
import "./tailwind.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

// headlines on Radar's front page
const newsreader = Newsreader({
  variable: "--font-serif",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Kompas",
  description: "AI watches the market. You grow.",
  icons: {
    icon: "/kompas_logo.png",
    shortcut: "/kompas_logo.png",
    apple: "/kompas_logo.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Only Chromium renders SVG filters in backdrop-filter; elsewhere the glass falls back to plain blur. */}
        <script dangerouslySetInnerHTML={{ __html: "if(window.chrome)document.documentElement.classList.add('lg-refract')" }} />
      </head>
      <body className={`${geistSans.variable} ${geistMono.variable}`}>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
