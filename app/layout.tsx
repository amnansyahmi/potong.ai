import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "potong.ai — potong video panjang jadi clip pendek",
  description: "Tampal URL YouTube atau upload video untuk mencari momen terbaik, menjana subtitle dan eksport clip 9:16 secara lokal.",
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
