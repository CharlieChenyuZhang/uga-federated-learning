import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "Campus | Federated Learning Lab",
  description:
    "A local research workspace for private campus datasets, small language model tuning, and transparent evaluation.",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
