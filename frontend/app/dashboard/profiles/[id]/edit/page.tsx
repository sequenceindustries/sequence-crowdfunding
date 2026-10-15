"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import ImageUpload from "@/components/ImageUpload";

type Profile = {
  id: number; slug: string; name: string; industry: string | null;
  stage: string | null; country: string | null; province: string | null; city: string | null;
  website: string | null; description: string | null; problem: string | null;
  solution: string | null; target_customers: string | null; business_model: string | null;
  competitive_advantage: string | null; founded_on: string | null;
  contact_is_public: boolean; public_contact_email: string | null;
  logo_image_token?: string | null;
};

export default function EditProfile() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [p, setP] = useState<Profile | null | undefined>(undefined);
  const [logoToken, setLogoToken] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ kind: "error" | "info"; text: string } | null>(null);

  useEffect(() => {
    let alive = true;
    api<{ profiles: Profile[] }>("/profiles/mine").then((r) => {
      if (!alive) return;
      const found = r.data?.profiles?.find((x) => String(x.id) === id) ?? null;
      setP(found);
      setLogoToken(found?.logo_image_token ?? null);
    });
    return () => { alive = false; };
  }, [id]);

  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setMsg(null);
    const f = new FormData(e.currentTarget);
    const s = (k: string) => (f.get(k) as string | null)?.trim() || null;
    const body = {
      name: s("name") ?? "",
      industry: s("industry"), stage: s("stage"),
      country: s("country"), province: s("province"), city: s("city"),
      website: s("website"), description: s("description"), problem: s("problem"),
      solution: s("solution"), target_customers: s("target_customers"),
      business_model: s("business_model"), competitive_advantage: s("competitive_advantage"),
      founded_on: s("founded_on"),
      contact_is_public: f.get("contact_is_public") === "on",
      public_contact_email: s("public_contact_email"),
    };
    const r = await api<{ message?: string }>(`/profiles/${id}`, { method: "PATCH", body });
    if (!r.ok) return setMsg({ kind: "error", text: r.data?.message ?? "Could not save." });
    setMsg({ kind: "info", text: "Saved." });
  }

  if (p === undefined) return <div className="container section">Loading…</div>;
  if (p === null) return (
    <div className="container section stack">
      <p>Profile not found. <Link href="/dashboard">Back</Link></p>
    </div>
  );

  const v = (x: string | null | undefined) => x ?? "";

  return (
    <div className="container section stack" style={{ maxWidth: 760 }}>
      <p><Link href="/dashboard">← Dashboard</Link></p>
      <h1>Edit business profile</h1>
      {msg && <div className={`alert ${msg.kind === "error" ? "alert-error" : "alert-info"}`} role="status">{msg.text}</div>}

      <form onSubmit={save} className="stack">
        <section className="card stack">
          <h2 style={{ marginTop: 0 }}>Basic info</h2>
          <div className="field"><label htmlFor="name">Business name *</label>
            <input id="name" name="name" required maxLength={200} defaultValue={p.name} /></div>
          <div className="row">
            <div className="field"><label htmlFor="industry">Industry</label>
              <input id="industry" name="industry" maxLength={100} defaultValue={v(p.industry)} /></div>
            <div className="field"><label htmlFor="stage">Stage</label>
              <input id="stage" name="stage" maxLength={60} placeholder="idea, pilot, trading…" defaultValue={v(p.stage)} /></div>
          </div>
          <div className="row">
            <div className="field"><label htmlFor="city">City</label>
              <input id="city" name="city" maxLength={80} defaultValue={v(p.city)} /></div>
            <div className="field"><label htmlFor="province">Province / Region</label>
              <input id="province" name="province" maxLength={80} defaultValue={v(p.province)} /></div>
            <div className="field"><label htmlFor="country">Country</label>
              <input id="country" name="country" maxLength={80} defaultValue={v(p.country) || "South Africa"} /></div>
          </div>
          <div className="field"><label htmlFor="founded_on">Founded on</label>
            <input id="founded_on" name="founded_on" type="date" defaultValue={v(p.founded_on)} /></div>
          <div className="field"><label htmlFor="website">Website</label>
            <input id="website" name="website" type="url" maxLength={255} placeholder="https://…" defaultValue={v(p.website)} /></div>

          <div className="field">
            <ImageUpload
              label="Business logo"
              previewUrl={logoToken ? `/api/public/images/${logoToken}` : null}
              onUploaded={(token) => setLogoToken(token)}
              onRemoved={() => setLogoToken(null)}
              uploadUrl={`/api/profiles/${id}/logo`}
              deleteUrl={`/api/profiles/${id}/logo`}
            />
          </div>
        </section>

        <section className="card stack">
          <h2 style={{ marginTop: 0 }}>About the business</h2>
          <div className="field"><label htmlFor="description">Description</label>
            <textarea id="description" name="description" rows={5} defaultValue={v(p.description)} /></div>
          <div className="field"><label htmlFor="problem">The problem you solve</label>
            <textarea id="problem" name="problem" rows={4} defaultValue={v(p.problem)} /></div>
          <div className="field"><label htmlFor="solution">Your solution</label>
            <textarea id="solution" name="solution" rows={4} defaultValue={v(p.solution)} /></div>
          <div className="field"><label htmlFor="target_customers">Target customers</label>
            <textarea id="target_customers" name="target_customers" rows={3} defaultValue={v(p.target_customers)} /></div>
          <div className="field"><label htmlFor="business_model">Business model</label>
            <textarea id="business_model" name="business_model" rows={3} defaultValue={v(p.business_model)} /></div>
          <div className="field"><label htmlFor="competitive_advantage">Competitive advantage</label>
            <textarea id="competitive_advantage" name="competitive_advantage" rows={3} defaultValue={v(p.competitive_advantage)} /></div>
        </section>

        <section className="card stack">
          <h2 style={{ marginTop: 0 }}>Contact</h2>
          <div className="field"><label htmlFor="public_contact_email">Public contact email</label>
            <input id="public_contact_email" name="public_contact_email" type="email" maxLength={255} defaultValue={v(p.public_contact_email)} /></div>
          <div className="field row" style={{ alignItems: "center", gap: "0.5rem" }}>
            <input id="contact_is_public" name="contact_is_public" type="checkbox" defaultChecked={p.contact_is_public} style={{ width: "auto" }} />
            <label htmlFor="contact_is_public" style={{ fontWeight: "normal" }}>Show contact email on public profile</label>
          </div>
          <p className="muted" style={{ fontSize: "0.85rem" }}>Shown only when your business has at least one published campaign.</p>
        </section>

        <div className="row">
          <button className="btn" type="submit">Save profile</button>
          <button type="button" className="btn btn-secondary" onClick={() => router.push("/dashboard")}>Done</button>
        </div>
      </form>
    </div>
  );
}
