import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "AEGIS Operations",
  description: "Sprint 0 internal operations dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
