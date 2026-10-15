"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Profile = { id: number; name: string };

export default function NewCampaign() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [rows, setRows] = useState([{ item: "", rand: "" }]);

  useEffect(() => { api<{ profiles: Profile[] }>("/profiles/mine").then((r) => setProfiles(r.data?.profiles ?? [])); }, []);

  const toCents = (v: string) => Math.round(parseFloat(v || "0") * 100);

  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    const f = new FormData(e.currentTarget);
    const body = {
      profile_id: Number(f.get("profile_id")), title: f.get("title"), summary: f.get("summary"),
      description: f.get("description"), funding_model: f.get("funding_model"),
      goal_cents: toCents(String(f.get("goal"))) || null,
      use_of_funds: rows.filter((r) => r.item.trim()).map((r) => ({ item: r.item.trim(), amount_cents: toCents(r.rand) })),
    };
    const r = await api<{ message?: string }>("/campaigns", { body });
    if (!r.ok) return setError(r.data?.message ?? "Could not save the draft.");
    window.location.href = "/dashboard";
  }

  return (
    <div className="container section stack" style={{ maxWidth: 720 }}>
      <h1>New campaign</h1>
      <p className="muted">Saved as a draft. You can edit it and submit for review when it is complete.</p>
      {error && <div className="alert alert-error" role="alert">{error}</div>}
      <form onSubmit={save} className="card">
        <div className="field"><label htmlFor="profile_id">Business profile</label>
          <select id="profile_id" name="profile_id" required>{profiles.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></div>
        <div className="field"><label htmlFor="title">Campaign title</label><input id="title" name="title" required maxLength={200} /></div>
        <div className="field"><label htmlFor="summary">One-sentence summary</label><input id="summary" name="summary" maxLength={400} /></div>
        <div className="field"><label htmlFor="description">Description</label><textarea id="description" name="description" />
          <span className="hint">At least 100 characters. Describe the problem, your solution, and what supporters help you do.</span></div>
        <div className="field"><label htmlFor="funding_model">Funding model</label>
          <select id="funding_model" name="funding_model" defaultValue="business_support">
            <option value="business_support">Business support</option><option value="reward">Reward</option><option value="donation">Donation</option>
          </select>
          <span className="hint">Supporters do not receive shares, interest or financial returns.</span></div>
        <div className="field"><label htmlFor="goal">Funding goal (R)</label><input id="goal" name="goal" type="number" min="1" step="1" /></div>
        <fieldset className="field" style={{ border: 0, padding: 0 }}>
          <legend style={{ fontWeight: 600 }}>Use of funds (must add up to the goal)</legend>
          {rows.map((r, i) => (
            <div className="row" key={i}>
              <input aria-label={`Item ${i + 1}`} placeholder="Item" value={r.item} onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, item: e.target.value } : x))} style={{ flex: "2 1 200px" }} />
              <input aria-label={`Amount ${i + 1} in rand`} placeholder="Amount (R)" type="number" min="0" value={r.rand} onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, rand: e.target.value } : x))} style={{ flex: "1 1 120px" }} />
            </div>
          ))}
          <button type="button" className="btn btn-secondary" onClick={() => setRows([...rows, { item: "", rand: "" }])}>Add line</button>
        </fieldset>
        <button className="btn" type="submit">Save draft</button>
      </form>
    </div>
  );
}
