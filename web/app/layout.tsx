import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Fraud Stream Detection",
  description: "Transactions scored as they arrive, ranked for a fixed daily review budget.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
