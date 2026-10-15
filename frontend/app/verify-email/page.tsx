import type { Metadata } from "next";
import TokenAction from "@/components/TokenAction";

export const metadata: Metadata = { title: "Confirm your email", robots: { index: false }, referrer: "no-referrer" };

export default async function VerifyEmail({ searchParams }: { searchParams: Promise<{ token?: string }> }) {
  const { token } = await searchParams;
  return (
    <div className="container section stack">
      <h1>Confirm your email</h1>
      <TokenAction token={typeof token === "string" ? token : ""} mode="verify" />
    </div>
  );
}
