import type { Metadata } from "next";
import { Libre_Baskerville } from "next/font/google";
import { Analytics } from "@vercel/analytics/react";
import "./globals.css";

const libreBaskerville = Libre_Baskerville({
  weight: ["400", "700"],
  subsets: ["latin"],
  variable: "--font-libre-baskerville",
});

export const metadata: Metadata = {
  title: "Bangers",
  description: "Top quoted tweets archive",
  icons: {
    icon: '/favicon.svg',
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${libreBaskerville.variable} font-serif antialiased bg-white text-black`}
      >
        {children}
        <Analytics />
      </body>
    </html>
  );
}
