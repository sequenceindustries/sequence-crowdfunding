"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

type Doc = { id: number; kind: string; filename: string; status: string; reviewer_note: string | null; created_at: string };

const KINDS: Record<string, string> = {
  identity: "Identity document",
  business_registration: "Business registration",
  proof_of_address: "Proof of address",
  bank_confirmation: "Bank confirmation letter",
};
const STATUS: Record<string, string> = {
  pending: "Waiting for review", approved: "Approved", rejected: "Rejected",
  info_requested: "More information needed", escalated: "With a senior reviewer",
};

export default function Verification() {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [msg, setMsg] = useState<{ kind: "error" | "info"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const r = await api<{ documents: Doc[] }>("/verification/documents");
    if (r.ok) setDocs(r.data.documents);
  }, []);
  useEffect(() => { let alive = true; api<{ documents: Doc[] }>("/verification/documents").then((r) => { if (alive && r.ok) setDocs(r.data.documents); }); return () => { alive = false; }; }, []);

  async function upload(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    setBusy(true); setMsg(null);
    const r = await api<{ message?: string; error?: string }>("/verification/documents", { form: new FormData(form) });
    setBusy(false);
    if (!r.ok) return setMsg({ kind: "error", text: r.data?.message ?? (r.data?.error === "too_many_documents" ? "You have reached the document limit. Delete one first." : "Upload failed.") });
    form.reset();
    setMsg({ kind: "info", text: "Uploaded. A reviewer will look at it; nothing is confirmed until they do." });
    load();
  }

  async function remove(id: number) {
    const r = await api(`/verification/documents/${id}`, { method: "DELETE" });
    setMsg(r.ok ? { kind: "info", text: "Document deleted." } : { kind: "error", text: "Approved documents are kept for the record." });
    load();
  }

  return (
    <div className="container section stack" style={{ maxWidth: 760 }}>
      <h1>Verification documents</h1>
      <p className="muted">PDF, PNG or JPG, up to 15 MB. Files are stored privately. Only platform reviewers can open them, and every time one is opened it is logged.</p>
      <p className="alert alert-warn">Approval of a document adds one badge to your campaign for that item only. It does not mean your claims or finances have been verified.</p>
      {msg && <div className={`alert ${msg.kind === "error" ? "alert-error" : "alert-info"}`} role="status">{msg.text}</div>}
      <form onSubmit={upload} className="card stack">
        <div className="field"><label htmlFor="kind">Document type</label>
          <select id="kind" name="kind" required>{Object.entries(KINDS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
        <div className="field"><label htmlFor="file">File</label><input id="file" name="file" type="file" accept=".pdf,.png,.jpg,.jpeg" required /></div>
        <button className="btn" type="submit" disabled={busy}>{busy ? "Uploading…" : "Upload"}</button>
      </form>
      <section className="card stack">
        <h2>Your documents</h2>
        {docs.length === 0 ? <div className="empty">Nothing uploaded yet.</div> : (
          <table>
            <thead><tr><th>Type</th><th>File</th><th>Status</th><th></th></tr></thead>
            <tbody>{docs.map((d) => (
              <tr key={d.id}>
                <td>{KINDS[d.kind] ?? d.kind}</td>
                <td>{d.filename}</td>
                <td><span className="badge">{STATUS[d.status] ?? d.status}</span>{d.reviewer_note && <div className="muted">Reviewer: {d.reviewer_note}</div>}</td>
                <td>{d.status !== "approved" && <button className="btn btn-secondary" onClick={() => remove(d.id)}>Delete</button>}</td>
              </tr>))}</tbody>
          </table>)}
      </section>
    </div>
  );
}
