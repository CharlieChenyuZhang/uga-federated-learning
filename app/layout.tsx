import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "Campus | Collaborative AI Lab",
  description:
    "A collaborative AI lab for campuses, research teams, and educators to explore ideas through independent local experiments.",
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
