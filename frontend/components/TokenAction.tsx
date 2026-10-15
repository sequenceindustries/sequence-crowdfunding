"use client";
import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";

/** Single-use links are redeemed by a button press, not on page load, so mail scanners that
 *  pre-fetch links cannot use them up. */
export default function TokenAction({ token, mode }: { token: string; mode: "verify" | "reset" }) {
  const [state, setState] = useState<"idle" | "busy" | "done" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);

  async function run(password?: string) {
    setState("busy");
    setMessage(null);
    const r = await api<{ message?: string }>(mode === "verify" ? "/auth/verify-email" : "/auth/reset-password", {
      body: mode === "verify" ? { token } : { token, password },
    });
    if (r.ok) return setState("done");
    setState("error");
    setMessage(r.data?.message ?? "This link is invalid or has expired. Request a new one.");
  }

  if (!token) return <div className="alert alert-error" role="alert">This link is missing its token. Request a new email.</div>;
  if (state === "done")
    return (
      <div className="alert alert-info" role="status">
        {mode === "verify" ? "Your email address is confirmed." : "Your password has been changed. Log in with the new one."}{" "}
        <Link href={mode === "verify" ? "/dashboard" : "/login"}>Continue</Link>
      </div>
    );
  return (
    <div className="stack">
      {state === "error" && <div className="alert alert-error" role="alert">{message}</div>}
      {mode === "verify" ? (
        <button className="btn" onClick={() => run()} disabled={state === "busy"}>Confirm my email</button>
      ) : (
        <form className="card" style={{ maxWidth: 440 }} onSubmit={(e) => { e.preventDefault(); run(String(new FormData(e.currentTarget).get("password"))); }}>
          <div className="field">
            <label htmlFor="password">New password</label>
            <input id="password" name="password" type="password" required autoComplete="new-password" />
            <span className="hint">At least 10 characters, with upper and lower case letters and a number.</span>
          </div>
          <button className="btn" type="submit" disabled={state === "busy"}>Change password</button>
        </form>
      )}
    </div>
  );
}
