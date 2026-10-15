"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Report = {
  checks: { field: string; severity: string; message: string }[];
  compliance_flags: { phrase: string; message: string }[];
  strengths: string[]; disclaimers: string[];
};
type Section = { key: string; heading: string; body: string; source: string };
type T = { status: string; sections: Section[]; live_sections: Section[]; owner_notes: { risks?: string; update_plan?: string }; stale: boolean };

export default function Assistant() {
  const { id } = useParams<{ id: string }>();
  const [report, setReport] = useState<Report | null>(null);
  const [t, setT] = useState<T | null>(null);
  const [msg, setMsg] = useState<{ kind: "error" | "info"; text: string } | null>(null);

  useEffect(() => {
    let alive = true;
    api<{ transparency: T | null }>(`/campaigns/${id}/transparency`).then((r) => { if (alive && r.ok) setT(r.data.transparency); });
    return () => { alive = false; };
  }, [id]);

  async function runReview() {
    setMsg(null);
    const r = await api<{ report: Report; error?: string }>(`/campaigns/${id}/assistant/review`, { body: {} });
    if (!r.ok) return setMsg({ kind: "error", text: r.status === 429 ? "Daily limit reached." : "The review is unavailable right now." });
    setReport(r.data.report);
  }

  async function makeDraft(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const r = await api<{ transparency: T; message?: string }>(`/campaigns/${id}/transparency/draft`, {
      body: { owner_notes: { risks: f.get("risks"), update_plan: f.get("update_plan") } },
    });
    if (!r.ok) return setMsg({ kind: "error", text: r.data?.message ?? "Could not create the draft." });
    setT(r.data.transparency);
    setMsg({ kind: "info", text: "Draft created. It is private until you approve it." });
  }

  async function approve() {
    const r = await api<{ transparency: T; message?: string }>(`/campaigns/${id}/transparency/approve`, { body: {} });
    if (!r.ok) return setMsg({ kind: "error", text: r.data?.message ?? "Could not approve." });
    setT(r.data.transparency);
    setMsg({ kind: "info", text: "Approved. It appears on the public page once the campaign is published." });
  }

  async function withdraw() {
    await api(`/campaigns/${id}/transparency`, { method: "DELETE" });
    setT(null);
    setMsg({ kind: "info", text: "Statement removed." });
  }

  return (
    <div className="container section stack" style={{ maxWidth: 800 }}>
      <p><Link href="/dashboard">← Dashboard</Link></p>
      <h1>Improve your campaign</h1>
      {msg && <div className={`alert ${msg.kind === "error" ? "alert-error" : "alert-info"}`} role="status">{msg.text}</div>}

      <section className="card stack">
        <h2>Campaign check</h2>
        <p className="muted">A rule-based check of completeness and wording. It does not rewrite anything and cannot tell whether your claims are true.</p>
        <div><button className="btn" onClick={runReview}>Run check</button></div>
        {report && (
          <div className="stack" aria-live="polite">
            {report.compliance_flags.map((f) => <div key={f.phrase} className="alert alert-error"><strong>“{f.phrase}”</strong> {f.message}</div>)}
            {report.checks.length === 0 && report.compliance_flags.length === 0 && <p>No issues found by these rules.</p>}
            {report.checks.length > 0 && <ul>{report.checks.map((c, i) => <li key={i}><span className="badge">{c.severity}</span> {c.message}</li>)}</ul>}
            {report.strengths.length > 0 && <><h3>Already in place</h3><ul>{report.strengths.map((s) => <li key={s}>{s}</li>)}</ul></>}
            {report.disclaimers.map((d) => <p key={d} className="muted">{d}</p>)}
          </div>)}
      </section>

      <section className="card stack">
        <h2>Transparency statement</h2>
        <p className="muted">Built only from the figures you entered, plus fixed platform wording about what a contribution is. Nothing is added about your business. It stays private until you approve it, and approval is withdrawn if you change the campaign.</p>
        <form onSubmit={makeDraft} className="stack">
          <div className="field"><label htmlFor="risks">Risks, in your own words (optional)</label><textarea id="risks" name="risks" rows={3} defaultValue={t?.owner_notes?.risks ?? ""} maxLength={2000} /></div>
          <div className="field"><label htmlFor="update_plan">How you will share progress updates (optional)</label><textarea id="update_plan" name="update_plan" rows={3} defaultValue={t?.owner_notes?.update_plan ?? ""} maxLength={2000} /></div>
          <div><button className="btn btn-secondary" type="submit">{t ? "Regenerate draft" : "Create draft"}</button></div>
        </form>
        {t && (
          <div className="stack">
            <p><span className="badge">{t.status}</span> {t.stale && <span className="badge badge-warn">Out of date: regenerate</span>}</p>
            {[...t.sections, ...t.live_sections].map((s) => <div key={s.key}><h3>{s.heading}</h3><p style={{ whiteSpace: "pre-wrap" }}>{s.body}</p></div>)}
            <div className="row">
              {t.status === "draft" && !t.stale && <button className="btn" onClick={approve}>Approve for publication</button>}
              <button className="btn btn-secondary" onClick={withdraw}>Remove</button>
            </div>
          </div>)}
      </section>
    </div>
  );
}
