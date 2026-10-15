"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Update = { id: number; title: string; body: string; created_at: string; hidden: boolean };

export default function CampaignUpdates() {
  const { id } = useParams<{ id: string }>();
  const [updates, setUpdates] = useState<Update[] | null>(null);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [msg, setMsg] = useState<{ kind: "error" | "info"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    const r = await api<{ updates: Update[] }>(`/campaigns/${id}/updates`);
    if (r.ok) setUpdates(r.data.updates);
  }

  useEffect(() => { load(); }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  async function post(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim() || !body.trim()) return;
    setBusy(true); setMsg(null);
    const r = await api<{ message?: string }>(`/campaigns/${id}/updates`, {
      body: { title: title.trim(), body: body.trim() },
    });
    setBusy(false);
    if (!r.ok) return setMsg({ kind: "error", text: r.data?.message ?? "Could not post update." });
    setTitle(""); setBody("");
    setMsg({ kind: "info", text: "Update posted." });
    load();
  }

  async function del(updateId: number) {
    if (!confirm("Delete this update? This cannot be undone.")) return;
    const r = await api(`/campaigns/${id}/updates/${updateId}`, { method: "DELETE" });
    if (!r.ok) return setMsg({ kind: "error", text: "Could not delete." });
    setUpdates((prev) => prev?.filter((u) => u.id !== updateId) ?? null);
  }

  return (
    <div className="container section stack" style={{ maxWidth: 720 }}>
      <p><Link href="/dashboard">← Dashboard</Link></p>
      <h1>Campaign updates</h1>
      <p className="muted">Updates appear publicly on the campaign page. Post when there is real progress to share. Updates are labelled as reported by you and not independently verified.</p>
      {msg && <div className={`alert ${msg.kind === "error" ? "alert-error" : "alert-info"}`} role="status">{msg.text}</div>}

      <section className="card stack">
        <h2 style={{ marginTop: 0 }}>Post a new update</h2>
        <form onSubmit={post} className="stack">
          <div className="field"><label htmlFor="utitle">Title</label>
            <input id="utitle" required maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} /></div>
          <div className="field"><label htmlFor="ubody">Body</label>
            <textarea id="ubody" required rows={6} maxLength={5000} value={body} onChange={(e) => setBody(e.target.value)} /></div>
          <div><button className="btn" type="submit" disabled={busy}>{busy ? "Posting…" : "Post update"}</button></div>
        </form>
      </section>

      <section className="stack">
        <h2>Posted updates</h2>
        {updates === null ? <p className="muted">Loading…</p> :
          updates.length === 0 ? <p className="muted">No updates yet. Updates are visible on your campaign page once posted.</p> :
          updates.map((u) => (
            <article key={u.id} className="card stack">
              <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <h3 style={{ margin: 0 }}>{u.title}</h3>
                  <p className="muted" style={{ fontSize: "0.85rem", margin: "0.25rem 0 0" }}>
                    {new Date(u.created_at).toLocaleDateString("en-ZA")}
                    {u.hidden && <span className="badge" style={{ marginLeft: "0.5rem", background: "#f00", color: "#fff" }}>Hidden by staff</span>}
                  </p>
                </div>
                {!u.hidden && (
                  <button className="btn btn-secondary" style={{ fontSize: "0.85rem" }} onClick={() => del(u.id)}>Delete</button>
                )}
              </div>
              <p style={{ whiteSpace: "pre-wrap", margin: 0 }}>{u.body}</p>
            </article>
          ))
        }
      </section>
    </div>
  );
}
