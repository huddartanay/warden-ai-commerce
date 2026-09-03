import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Warden",
  description:
    "Deterministic trust and authorization layer between AI buyers and Razorpay.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
