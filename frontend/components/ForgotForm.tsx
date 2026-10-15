"use client";
import { useState } from "react";
import { api } from "@/lib/api";

export default function ForgotForm() {
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    await api("/auth/forgot-password", { body: { email: new FormData(e.currentTarget).get("email") } });
    setBusy(false);
    setSent(true);
  }

  if (sent)
    return <div className="alert alert-info" role="status">If an account exists for that email, a reset link is on its way. It works once and expires in an hour.</div>;
  return (
    <form onSubmit={onSubmit} className="card" style={{ maxWidth: 440 }}>
      <div className="field"><label htmlFor="email">Email</label><input id="email" name="email" type="email" required autoComplete="email" /></div>
      <button className="btn" type="submit" disabled={busy}>Send reset link</button>
    </form>
  );
}
