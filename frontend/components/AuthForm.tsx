"use client";
import { useState } from "react";
import { api } from "@/lib/api";

export default function AuthForm({ mode }: { mode: "login" | "register" }) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const f = new FormData(e.currentTarget);
    const body =
      mode === "login"
        ? { email: f.get("email"), password: f.get("password") }
        : { email: f.get("email"), password: f.get("password"), full_name: f.get("full_name"), role: f.get("role") };
    const r = await api<{ error?: string; message?: string }>(`/auth/${mode}`, { body });
    setBusy(false);
    if (!r.ok) {
      const map: Record<string, string> = {
        invalid_credentials: "Email or password is incorrect.",
        email_taken: "An account with that email already exists.",
        invalid_email: "Enter a valid email address.",
        rate_limited: "Too many attempts. Please wait and try again.",
      };
      setError(r.data?.message ?? map[r.data?.error ?? ""] ?? "Something went wrong. Please try again.");
      return;
    }
    window.location.href = "/dashboard";
  }

  return (
    <form onSubmit={onSubmit} className="card" style={{ maxWidth: 440 }} noValidate>
      {error && <div className="alert alert-error" role="alert">{error}</div>}
      {mode === "register" && (
        <>
          <div className="field"><label htmlFor="full_name">Full name</label><input id="full_name" name="full_name" required autoComplete="name" /></div>
          <div className="field">
            <label htmlFor="role">I want to</label>
            <select id="role" name="role" defaultValue="founder">
              <option value="founder">Create a campaign</option>
              <option value="supporter">Follow and support campaigns</option>
            </select>
          </div>
        </>
      )}
      <div className="field"><label htmlFor="email">Email</label><input id="email" name="email" type="email" required autoComplete="email" /></div>
      <div className="field">
        <label htmlFor="password">Password</label>
        <input id="password" name="password" type="password" required autoComplete={mode === "login" ? "current-password" : "new-password"} />
        {mode === "register" && <span className="hint">At least 10 characters, with upper and lower case letters and a number.</span>}
      </div>
      <button className="btn" type="submit" disabled={busy}>{busy ? "Please wait…" : mode === "login" ? "Log in" : "Create account"}</button>
    </form>
  );
}
