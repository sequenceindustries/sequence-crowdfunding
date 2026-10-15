"use client";
import { useCallback, useEffect, useState } from "react";
import { Campaign, api, formatRand } from "@/lib/api";

type VDoc = { id: number; kind: string; filename: string; status: string; owner: { email: string; full_name: string } };

function Decide({ actions, onDecide }: { actions: [string, string][]; onDecide: (action: string, reason: string) => void }) {
  const [reason, setReason] = useState("");
  return (
    <div className="stack">
      <label className="sr-only" htmlFor="reason">Reason (required, recorded)</label>
      <input placeholder="Reason (required, recorded)" value={reason} onChange={(e) => setReason(e.target.value)} />
      <div className="row">{actions.map(([a, label]) => (
        <button key={a} className="btn btn-secondary" disabled={!reason.trim()} onClick={() => { onDecide(a, reason); setReason(""); }}>{label}</button>))}</div>
    </div>
  );
}

async function fetchQueues() {
  const [c, v] = await Promise.all([
    api<{ campaigns: Campaign[] }>("/admin/review-queue"),
    api<{ documents: VDoc[] }>("/admin/verification/queue"),
  ]);
  return { ok: c.ok && v.ok, campaigns: c.data?.campaigns ?? [], docs: v.data?.documents ?? [] };
}

export default function Staff() {
  const [allowed, setAllowed] = useState<boolean | undefined>(undefined);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [docs, setDocs] = useState<VDoc[]>([]);
  const [msg, setMsg] = useState<string | null>(null);

  const apply = useCallback((q: Awaited<ReturnType<typeof fetchQueues>>) => { setAllowed(q.ok); setCampaigns(q.campaigns); setDocs(q.docs); }, []);
  const reload = useCallback(async () => apply(await fetchQueues()), [apply]);
  useEffect(() => { let alive = true; fetchQueues().then((q) => { if (alive) apply(q); }); return () => { alive = false; }; }, [apply]);

  async function decideCampaign(id: number, action: string, reason: string) {
    const r = await api(`/admin/campaigns/${id}/decision`, { body: { action, reason } });
    setMsg(r.ok ? "Decision recorded." : "That decision could not be applied.");
    reload();
  }
  async function decideDoc(id: number, action: string, reason: string) {
    const r = await api(`/admin/verification/documents/${id}/decision`, { body: { action, reason } });
    setMsg(r.ok ? "Decision recorded and the founder was emailed." : "That decision could not be applied.");
    reload();
  }
  async function openDoc(id: number) {
    const r = await api<{ url: string }>(`/admin/verification/documents/${id}/download-link`, { body: {} });
    if (r.ok) window.open(r.data.url, "_blank", "noopener");
    else setMsg("You cannot open that document.");
  }

  if (allowed === undefined) return <div className="container section">Loading…</div>;
  if (!allowed) return <div className="container section"><p>This area is for platform reviewers.</p></div>;

  return (
    <div className="container section stack">
      <h1>Review desk</h1>
      {msg && <div className="alert alert-info" role="status">{msg}</div>}
      <section className="card stack">
        <h2>Campaigns awaiting review ({campaigns.length})</h2>
        {campaigns.length === 0 && <div className="empty">Nothing waiting.</div>}
        {campaigns.map((c) => (
          <article key={c.id} className="card stack">
            <h3>{c.title}</h3>
            <p>{c.summary}</p>
            <p className="muted">{c.business.name} · goal {formatRand(c.goal_cents)} · {c.funding_model}</p>
            <ul>{c.use_of_funds.map((u) => <li key={u.item}>{u.item}: {formatRand(u.amount_cents)}</li>)}</ul>
            <details><summary>Full description</summary><p style={{ whiteSpace: "pre-wrap" }}>{c.description}</p></details>
            <Decide actions={[["approve", "Approve"], ["request_changes", "Request changes"], ["reject", "Reject"]]} onDecide={(a, r) => decideCampaign(c.id, a, r)} />
          </article>))}
      </section>
      <section className="card stack">
        <h2>Verification documents ({docs.length})</h2>
        {docs.length === 0 && <div className="empty">Nothing waiting.</div>}
        {docs.map((d) => (
          <article key={d.id} className="card stack">
            <p><strong>{d.kind.replace("_", " ")}</strong> · {d.filename} · {d.owner.full_name} ({d.owner.email}) {d.status === "escalated" && <span className="badge badge-warn">escalated</span>}</p>
            <div><button className="btn btn-secondary" onClick={() => openDoc(d.id)}>Open document (logged)</button></div>
            <Decide actions={[["approve", "Approve"], ["request_info", "Request info"], ["reject", "Reject"], ...(d.status === "pending" ? [["escalate", "Escalate"] as [string, string]] : [])]} onDecide={(a, r) => decideDoc(d.id, a, r)} />
          </article>))}
      </section>
    </div>
  );
}
