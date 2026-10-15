import type { Metadata } from "next";

// Private founder pages must never be indexed.
export const metadata: Metadata = { title: "Dashboard", robots: { index: false, follow: false } };

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return children;
}
