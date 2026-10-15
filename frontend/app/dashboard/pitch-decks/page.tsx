"use client";
import { useState } from "react";
import { api } from "@/lib/api";

type Report = {
  provider: string;
  overall_completeness_score: number;
  category_scores: Record<string, number>;
  strengths: string[]; weaknesses: string[]; missing_sections: string[]; unclear_claims: string[];
  financial_assumptions_to_validate: string[]; recommendations: string[]; next_steps: string[];
  methodology: { type: string; scoring: string }; disclaimers: string[];
};

export default function PitchDecks() {
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [report, setReport] = useState<Report | null>(null);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null); setReport(null); setStatus("Uploading…");
    const up = await api<{ pitch_deck?: { id: number; status: string; error?: string }; message?: string }>("/pitch-decks", { form: new FormData(e.currentTarget) });
    if (!up.ok || !up.data.pitch_deck) { setStatus(null); return setError(up.data?.message ?? "Upload failed."); }
    if (up.data.pitch_deck.status !== "ready") { setStatus(null); return setError(up.data.pitch_deck.error ?? "No readable text found in this file."); }
    setStatus("Analysing…");
    const an = await api<{ report: Report; error?: string }>(`/pitch-decks/${up.data.pitch_deck.id}/analyse`, { body: {} });
    setStatus(null);
    if (!an.ok) return setError(an.status === 429 ? "Daily analysis limit reached." : "The analysis is unavailable right now.");
    setReport(an.data.report);
  }

  return (
    <div className="container section stack" style={{ maxWidth: 760 }}>
      <h1>Pitch-deck check</h1>
      <p className="muted">PDF or PPTX, up to 15 MB. Your file is stored privately and is visible only to you.</p>
      <p className="alert alert-info">No charge is made for this check at present.</p>
      {error && <div className="alert alert-error" role="alert">{error}</div>}
      {status && <div className="alert alert-info" role="status">{status}</div>}
      <form onSubmit={onSubmit} className="card">
        <div className="field"><label htmlFor="file">Pitch deck</label><input id="file" name="file" type="file" accept=".pdf,.pptx" required /></div>
        <button className="btn" type="submit" disabled={!!status}>Upload and analyse</button>
      </form>

      {report && (
        <section className="card stack" aria-live="polite">
          <h2>Completeness: {report.overall_completeness_score} / 100</h2>
          <div className="meter" aria-hidden><span style={{ width: `${report.overall_completeness_score}%` }} /></div>
          <p className="muted">{report.methodology.type}. {report.methodology.scoring}</p>
          {report.disclaimers.map((d) => <p key={d} className="alert alert-warn">{d}</p>)}
          {report.missing_sections.length > 0 && <><h3>Missing sections</h3><ul>{report.missing_sections.map((s) => <li key={s}>{s.replace("_", " ")}</li>)}</ul></>}
          {report.strengths.length > 0 && <><h3>Strengths</h3><ul>{report.strengths.map((s) => <li key={s}>{s}</li>)}</ul></>}
          {report.weaknesses.length > 0 && <><h3>Weaknesses</h3><ul>{report.weaknesses.map((s) => <li key={s}>{s}</li>)}</ul></>}
          {report.unclear_claims.length > 0 && <><h3>Claims needing evidence</h3><ul>{report.unclear_claims.map((s) => <li key={s}>{s}</li>)}</ul></>}
          {report.financial_assumptions_to_validate.length > 0 && <><h3>Financial points to validate</h3><ul>{report.financial_assumptions_to_validate.map((s) => <li key={s}>{s}</li>)}</ul></>}
          {report.recommendations.length > 0 && <><h3>Recommendations</h3><ul>{report.recommendations.map((s) => <li key={s}>{s}</li>)}</ul></>}
          <h3>Next steps</h3><ul>{report.next_steps.map((s) => <li key={s}>{s}</li>)}</ul>
        </section>
      )}
    </div>
  );
}
