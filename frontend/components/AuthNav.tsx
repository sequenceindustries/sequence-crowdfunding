"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Me = { user: { full_name: string; role: string } | null };

export default function AuthNav() {
  const [me, setMe] = useState<Me["user"] | undefined>(undefined);

  useEffect(() => {
    api<Me>("/auth/me").then((r) => setMe(r.data?.user ?? null));
  }, []);

  if (me === undefined) return <span className="sr-only">Loading account</span>;
  if (!me) {
    return (
      <>
        <Link href="/login">Log in</Link>
        <Link href="/register" className="btn">Start a campaign</Link>
      </>
    );
  }
  return (
    <>
      <Link href="/dashboard">Dashboard</Link>
      <button
        className="btn btn-secondary"
        onClick={async () => {
          await api("/auth/logout", { method: "POST", body: {} });
          window.location.href = "/";
        }}
      >
        Log out
      </button>
    </>
  );
}
