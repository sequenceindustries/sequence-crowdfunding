import type { Metadata } from "next";
import TokenAction from "@/components/TokenAction";

export const metadata: Metadata = { title: "Choose a new password", robots: { index: false }, referrer: "no-referrer" };

export default async function ResetPassword({ searchParams }: { searchParams: Promise<{ token?: string }> }) {
  const { token } = await searchParams;
  return (
    <div className="container section stack">
      <h1>Choose a new password</h1>
      <TokenAction token={typeof token === "string" ? token : ""} mode="reset" />
    </div>
  );
}
