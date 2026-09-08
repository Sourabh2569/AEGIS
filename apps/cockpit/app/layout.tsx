import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "AEGIS Cockpit",
  description: "Decision-support view: charts, real signals, and the reasoning behind them",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
