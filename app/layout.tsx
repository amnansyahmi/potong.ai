import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "potong.ai",
  description: "Potong video panjang jadi short-form clips.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ms">
      <body>{children}</body>
    </html>
  );
}
