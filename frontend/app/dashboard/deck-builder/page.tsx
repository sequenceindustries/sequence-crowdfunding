"use client";
import { useState } from "react";
import { api } from "@/lib/api";

type Slide = { id: string; key: string; title: string; body: string; bullets: string[]; incomplete: boolean; note: string | null; label: string | null };
type Draft = { id: number; title: string; theme: string; slides: Slide[]; themes: string[]; incomplete_count: number };

const QUESTIONS: [string, string, string][] = [
  ["business_name", "Business name", "line"],
  ["tagline", "One-line tagline (optional)", "line"],
  ["problem", "What problem do you solve, and for whom?", "text"],
  ["solution", "What do you offer, and how does it solve that problem?", "text"],
  ["product", "Describe your product or service (optional)", "text"],
  ["customers", "Who are your first customers? (optional)", "text"],
  ["market", "What do you know about your market? Only include what you can source. (optional)", "text"],
  ["competition", "Who else solves this, and how do you differ? (optional)", "text"],
  ["revenue_model", "How does the business earn money? (optional)", "text"],
  ["marketing", "How will you reach customers? (optional)", "text"],
  ["traction", "What progress can you prove? Leave empty if you are pre-launch. (optional)", "text"],
  ["financial_assumptions", "Your key financial assumptions, marked as estimates. (optional)", "text"],
  ["risks", "Main risks and how you would respond. (optional)", "text"],
];

export default function DeckBuilder() {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [msg, setMsg] = useState<{ kind: "error" | "info"; text: string } | null>(null);
  const [rows, setRows] = useState([{ item: "", rand: "" }]);

  const cents = (v: string) => Math.round(parseFloat(v || "0") * 100);

  async function create(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const answers: Record<string, unknown> = {};
    for (const [k] of QUESTIONS) answers[k] = f.get(k);
    const goal = cents(String(f.get("goal")));
    if (goal > 0) answers.funding_request_cents = goal;
    answers.use_of_funds = rows.filter((r) => r.item.trim()).map((r) => ({ item: r.item.trim(), amount_cents: cents(r.rand) }));
    const r = await api<{ draft: Draft; message?: string }>("/deck-drafts", { body: { answers } });
    if (!r.ok) return setMsg({ kind: "error", text: r.data?.message ?? "Could not create the draft." });
    setDraft(r.data.draft);
    setMsg(null);
  }

  async function save(slides: Slide[]) {
    if (!draft) return;
    const r = await api<{ draft: Draft; message?: string }>(`/deck-drafts/${draft.id}`, { method: "PATCH", body: { slides } });
    if (!r.ok) return setMsg({ kind: "error", text: r.data?.message ?? "Could not save." });
    setDraft(r.data.draft);
  }

  const edit = (i: number, patch: Partial<Slide>) => draft && save(draft.slides.map((s, j) => (j === i ? { ...s, ...patch } : s)));
  const move = (i: number, d: number) => {
    if (!draft) return;
    const s = [...draft.slides];
    const j = i + d;
    if (j < 0 || j >= s.length) return;
    [s[i], s[j]] = [s[j], s[i]];
    save(s);
  };

  async function regenerate(key: string) {
    if (!draft) return;
    if (!confirm("Rebuild this slide from your questionnaire answers? Your edits to it will be replaced.")) return;
    const r = await api<{ draft: Draft; message?: string }>(`/deck-drafts/${draft.id}/regenerate`, { body: { key } });
    if (!r.ok) return setMsg({ kind: "error", text: r.data?.message ?? "Could not regenerate." });
    setDraft(r.data.draft);
  }

  async function exportDeck(force: boolean) {
    if (!draft) return;
    const res = await fetch(`/api/deck-drafts/${draft.id}/export.pptx${force ? "?allow_incomplete=true" : ""}`, { credentials: "same-origin" });
    if (res.status === 409) {
      const j = await res.json();
      if (force || !confirm(`${j.message} (${(j.incomplete_slides ?? []).join(", ")}). Export anyway? Incomplete slides will be stamped as drafts.`)) return;
      return exportDeck(true);
    }
    if (!res.ok) return setMsg({ kind: "error", text: "Export failed." });
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = `${draft.title || "pitch-deck"}.pptx`;
    a.click();
    URL.revokeObjectURL(url);
  }

  if (!draft) {
    return (
      <div className="container section stack" style={{ maxWidth: 760 }}>
        <h1>Pitch-deck builder</h1>
        <p className="muted">
          Answer what you can. The builder arranges your own words into slides. It never adds facts, figures or claims, and
          anything missing is flagged for you to complete.
        </p>
        {msg && <div className={`alert ${msg.kind === "error" ? "alert-error" : "alert-info"}`} role="alert">{msg.text}</div>}
        <form onSubmit={create} className="card">
          {QUESTIONS.map(([k, label, kind]) => (
            <div className="field" key={k}>
              <label htmlFor={k}>{label}</label>
              {kind === "line" ? <input id={k} name={k} maxLength={300} /> : <textarea id={k} name={k} />}
            </div>
          ))}
          <div className="field"><label htmlFor="goal">Funding you are asking for (R)</label><input id="goal" name="goal" type="number" min="0" /></div>
          <fieldset className="field" style={{ border: 0, padding: 0 }}>
            <legend style={{ fontWeight: 600 }}>Use of funds (should add up to the amount asked for)</legend>
            {rows.map((r, i) => (
              <div className="row" key={i}>
                <input aria-label={`Item ${i + 1}`} placeholder="Item" value={r.item} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, item: e.target.value } : x)))} style={{ flex: "2 1 200px" }} />
                <input aria-label={`Amount ${i + 1} in rand`} placeholder="Amount (R)" type="number" min="0" value={r.rand} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, rand: e.target.value } : x)))} style={{ flex: "1 1 120px" }} />
              </div>
            ))}
            <button type="button" className="btn btn-secondary" onClick={() => setRows([...rows, { item: "", rand: "" }])}>Add line</button>
          </fieldset>
          <button className="btn" type="submit">Build my draft</button>
        </form>
      </div>
    );
  }

  return (
    <div className="container section stack" style={{ maxWidth: 820 }}>
      <h1>{draft.title}</h1>
      {msg && <div className="alert alert-error" role="alert">{msg.text}</div>}
      {draft.incomplete_count > 0 && (
        <div className="alert alert-warn">{draft.incomplete_count} slide{draft.incomplete_count === 1 ? "" : "s"} still need attention before this deck is ready to share.</div>
      )}
      <div className="row">
        <label htmlFor="theme">Theme</label>
        <select id="theme" value={draft.theme} style={{ width: "auto" }} onChange={async (e) => {
          const r = await api<{ draft: Draft }>(`/deck-drafts/${draft.id}`, { method: "PATCH", body: { theme: e.target.value } });
          if (r.ok) setDraft(r.data.draft);
        }}>
          {draft.themes.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <button className="btn" onClick={() => exportDeck(false)}>Export PowerPoint</button>
        <button className="btn btn-secondary" onClick={() => save([...draft.slides, { id: "", key: "custom", title: "New slide", body: "", bullets: [], incomplete: true, note: null, label: null }])}>Add slide</button>
      </div>

      {draft.slides.map((s, i) => (
        <section key={s.id} className="card stack" aria-label={`Slide ${i + 1}`}>
          {s.incomplete && <div className="alert alert-warn" role="status">{s.note ?? "This slide needs content."}</div>}
          <div className="field"><label htmlFor={`t-${s.id}`}>Slide {i + 1} title</label>
            <input id={`t-${s.id}`} defaultValue={s.title} onBlur={(e) => e.target.value !== s.title && edit(i, { title: e.target.value })} /></div>
          <div className="field"><label htmlFor={`b-${s.id}`}>Points (one per line)</label>
            <textarea id={`b-${s.id}`} defaultValue={s.bullets.join("\n")} onBlur={(e) => {
              const next = e.target.value.split("\n").map((l) => l.trim()).filter(Boolean);
              if (next.join("\n") !== s.bullets.join("\n")) edit(i, { bullets: next });
            }} /></div>
          {s.label && <p className="muted" style={{ fontStyle: "italic" }}>{s.label}</p>}
          <div className="row">
            <button className="btn btn-secondary" onClick={() => move(i, -1)} disabled={i === 0} aria-label={`Move slide ${i + 1} up`}>↑</button>
            <button className="btn btn-secondary" onClick={() => move(i, 1)} disabled={i === draft.slides.length - 1} aria-label={`Move slide ${i + 1} down`}>↓</button>
            {s.key !== "custom" && <button className="btn btn-secondary" onClick={() => regenerate(s.key)}>Rebuild from answers</button>}
            <button className="btn btn-danger" onClick={() => save(draft.slides.filter((_, j) => j !== i))}>Remove</button>
          </div>
        </section>
      ))}
    </div>
  );
}
