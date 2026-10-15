"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Campaign, api } from "@/lib/api";
import ImageUpload from "@/components/ImageUpload";

type Fund = { item: string; rand: string };
type Ms = { title: string; detail: string; target_date: string };

const toCents = (v: string) => Math.round(parseFloat(v || "0") * 100);
const toRand = (c: number) => String(Math.round(c) / 100);

export default function EditCampaign() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [c, setC] = useState<Campaign | null | undefined>(undefined);
  const [funds, setFunds] = useState<Fund[]>([]);
  const [ms, setMs] = useState<Ms[]>([]);
  const [msg, setMsg] = useState<{ kind: "error" | "info"; text: string } | null>(null);
  const [coverToken, setCoverToken] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api<{ campaign: Campaign }>(`/campaigns/${id}`).then((r) => {
      if (!alive) return;
      if (!r.ok) return setC(null);
      const camp = r.data.campaign;
      setC(camp);
      setCoverToken(camp.cover_image_token ?? null);
      setFunds(camp.use_of_funds.map((u) => ({ item: u.item, rand: toRand(u.amount_cents) })));
      setMs(camp.milestones.map((m) => ({ title: m.title, detail: m.detail ?? "", target_date: m.target_date ?? "" })));
    });
    return () => { alive = false; };
  }, [id]);

  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setMsg(null);
    const f = new FormData(e.currentTarget);
    const s = (k: string) => String(f.get(k) ?? "");
    const goal = toCents(s("goal"));
    const days = parseInt(s("duration_days"), 10);
    const body = {
      title: s("title"), summary: s("summary"), description: s("description"), category: s("category"),
      location: s("location"), stage: s("stage"), objectives: s("objectives"), funding_purpose: s("funding_purpose"),
      funding_model: s("funding_model"), goal_cents: goal || null, duration_days: Number.isFinite(days) ? days : null,
      use_of_funds: funds.filter((r) => r.item.trim()).map((r) => ({ item: r.item.trim(), amount_cents: toCents(r.rand) })),
      milestones: ms.filter((m) => m.title.trim()).map((m) => ({ title: m.title.trim(), detail: m.detail, target_date: m.target_date || null })),
    };
    const r = await api<{ message?: string }>(`/campaigns/${id}`, { method: "PATCH", body });
    if (!r.ok) return setMsg({ kind: "error", text: r.data?.message ?? "Could not save." });
    setMsg({ kind: "info", text: "Saved." });
  }

  if (c === undefined) return <div className="container section">Loading…</div>;
  if (c === null) return <div className="container section"><p>Campaign not found. <Link href="/dashboard">Back</Link></p></div>;
  if (c.status !== "draft" && c.status !== "changes_requested")
    return <div className="container section stack"><p className="alert alert-info">A {c.status.replace("_", " ")} campaign cannot be edited.</p><Link href="/dashboard">Back</Link></div>;

  const total = funds.reduce((n, r) => n + toCents(r.rand), 0);
  const goal = c.goal_cents ?? 0;
  const v = (x: string | null) => x ?? "";

  return (
    <div className="container section stack" style={{ maxWidth: 760 }}>
      <p><Link href="/dashboard">← Dashboard</Link></p>
      <h1>Edit campaign</h1>
      {c.review_note && <div className="alert alert-warn">Reviewer note: {c.review_note}</div>}
      {c.status === "changes_requested" && <p className="muted">After saving, go back to the dashboard and submit again.</p>}
      {msg && <div className={`alert ${msg.kind === "error" ? "alert-error" : "alert-info"}`} role="status">{msg.text}</div>}
      <form onSubmit={save} className="card">
        <div className="field"><label htmlFor="title">Title</label><input id="title" name="title" defaultValue={c.title} required maxLength={200} /></div>
        <div className="field"><label htmlFor="summary">Summary</label><input id="summary" name="summary" defaultValue={v(c.summary)} maxLength={400} /></div>

        <div className="field">
          <ImageUpload
            label="Cover image"
            previewUrl={coverToken ? `/api/public/images/${coverToken}` : null}
            onUploaded={(token) => setCoverToken(token)}
            onRemoved={() => setCoverToken(null)}
            uploadUrl={`/api/campaigns/${id}/cover-image`}
            deleteUrl={`/api/campaigns/${id}/cover-image`}
          />
        </div>

        <div className="field"><label htmlFor="description">Description</label><textarea id="description" name="description" rows={8} defaultValue={v(c.description)} /></div>
        <div className="field"><label htmlFor="category">Category</label><input id="category" name="category" defaultValue={v(c.category)} maxLength={100} /></div>
        <div className="row">
          <div className="field"><label htmlFor="location">Location</label><input id="location" name="location" defaultValue={v(c.location)} /></div>
          <div className="field"><label htmlFor="stage">Business stage</label><input id="stage" name="stage" defaultValue={v(c.stage)} placeholder="idea, pilot, trading…" /></div>
        </div>
        <div className="field"><label htmlFor="objectives">Objectives</label><textarea id="objectives" name="objectives" rows={3} defaultValue={v(c.objectives)} /></div>
        <div className="field"><label htmlFor="funding_purpose">What the funding is for</label><textarea id="funding_purpose" name="funding_purpose" rows={3} defaultValue={v(c.funding_purpose)} /></div>
        <div className="field"><label htmlFor="funding_model">Funding model</label>
          <select id="funding_model" name="funding_model" defaultValue={c.funding_model ?? "business_support"}>
            <option value="business_support">Business support</option><option value="reward">Reward</option><option value="donation">Donation</option>
          </select></div>
        <div className="row">
          <div className="field"><label htmlFor="goal">Funding goal (R)</label><input id="goal" name="goal" type="number" min="1" step="1" defaultValue={c.goal_cents ? toRand(c.goal_cents) : ""} /></div>
          <div className="field"><label htmlFor="duration_days">Duration (days)</label><input id="duration_days" name="duration_days" type="number" min="1" max="365" defaultValue={c.duration_days ?? ""} /></div>
        </div>

        <fieldset className="field" style={{ border: 0, padding: 0 }}>
          <legend style={{ fontWeight: 600 }}>Use of funds</legend>
          {funds.map((r, i) => (
            <div className="row" key={i}>
              <input aria-label={`Item ${i + 1}`} value={r.item} onChange={(e) => setFunds(funds.map((x, j) => j === i ? { ...x, item: e.target.value } : x))} style={{ flex: "2 1 200px" }} />
              <input aria-label={`Amount ${i + 1} in rand`} type="number" min="0" value={r.rand} onChange={(e) => setFunds(funds.map((x, j) => j === i ? { ...x, rand: e.target.value } : x))} style={{ flex: "1 1 120px" }} />
              <button type="button" className="btn btn-secondary" onClick={() => setFunds(funds.filter((_, j) => j !== i))}>Remove</button>
            </div>))}
          <button type="button" className="btn btn-secondary" onClick={() => setFunds([...funds, { item: "", rand: "" }])}>Add line</button>
          <span className="hint">Entered total: R{(total / 100).toLocaleString("en-ZA")}. {goal > 0 && total !== goal ? "This does not match the saved goal yet." : "It must equal the goal to submit."}</span>
        </fieldset>

        <fieldset className="field" style={{ border: 0, padding: 0 }}>
          <legend style={{ fontWeight: 600 }}>Milestones</legend>
          {ms.map((m, i) => (
            <div className="stack card" key={i}>
              <input aria-label={`Milestone ${i + 1} title`} placeholder="What will happen" value={m.title} onChange={(e) => setMs(ms.map((x, j) => j === i ? { ...x, title: e.target.value } : x))} />
              <textarea aria-label={`Milestone ${i + 1} detail`} placeholder="Detail (optional)" rows={2} value={m.detail} onChange={(e) => setMs(ms.map((x, j) => j === i ? { ...x, detail: e.target.value } : x))} />
              <input aria-label={`Milestone ${i + 1} target date`} type="date" value={m.target_date} onChange={(e) => setMs(ms.map((x, j) => j === i ? { ...x, target_date: e.target.value } : x))} />
              <div><button type="button" className="btn btn-secondary" onClick={() => setMs(ms.filter((_, j) => j !== i))}>Remove milestone</button></div>
            </div>))}
          <button type="button" className="btn btn-secondary" onClick={() => setMs([...ms, { title: "", detail: "", target_date: "" }])}>Add milestone</button>
        </fieldset>

        <div className="row"><button className="btn" type="submit">Save</button>
          <button type="button" className="btn btn-secondary" onClick={() => router.push("/dashboard")}>Done</button></div>
      </form>
    </div>
  );
}
