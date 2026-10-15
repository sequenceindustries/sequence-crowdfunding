"use client";
import Link from "next/link";
import { useState } from "react";
import { api, formatRand } from "@/lib/api";

type Result = { contribution: { status: string; simulated: boolean; amount_cents: number; label: string | null; provider_ref?: string }; checkout_url: string | null };

export default function ContributeBox({ slug, mode }: { slug: string; mode: "simulated" | "live" }) {
  // One key per page view: a double-click or retry replays the same payment instead of creating a second.
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const f = new FormData(e.currentTarget);
    const r = await api<Result & { message?: string; error?: string }>(`/campaigns/${slug}/contributions`, {
      body: { amount_cents: Math.round(parseFloat(String(f.get("amount") || "0")) * 100), accept_terms: f.get("terms") === "on" },
      headers: { "Idempotency-Key": idempotencyKey },
    });
    setBusy(false);
    if (r.status === 401) return setError("Please log in with a supporter account to contribute.");
    if (r.status === 403) return setError(r.data?.message ?? "Only confirmed supporter accounts can contribute.");
    if (!r.ok) return setError(r.data?.message ?? "Your contribution could not be started.");
    setResult(r.data);
    if (r.data.checkout_url) window.location.assign(r.data.checkout_url);
  }

  if (result)
    return (
      <div className="alert alert-info" role="status">
        {result.contribution.simulated
          ? `Test payment of ${formatRand(result.contribution.amount_cents)} recorded. No money moved.`
          : `Payment of ${formatRand(result.contribution.amount_cents)} started. It counts only once your payment provider confirms it.`}
      </div>
    );
  return (
    <form onSubmit={onSubmit} className="stack">
      {mode === "simulated" && <p className="alert alert-warn">Test mode: payments are simulated and no money moves.</p>}
      {error && <div className="alert alert-error" role="alert">{error} <Link href="/login">Log in</Link></div>}
      <div className="field"><label htmlFor="amount">Amount (R)</label><input id="amount" name="amount" type="number" min="20" max="50000" step="1" required /></div>
      <div className="row">
        <input id="terms" name="terms" type="checkbox" style={{ width: 20, minHeight: 20 }} required />
        <label htmlFor="terms">I understand this supports a project. It is not an investment and returns are not promised.</label>
      </div>
      <button className="btn" type="submit" disabled={busy}>Contribute</button>
    </form>
  );
}
