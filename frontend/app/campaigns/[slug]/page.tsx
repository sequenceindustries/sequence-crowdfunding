import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import ContributeBox from "@/components/ContributeBox";
import FollowButton from "@/components/FollowButton";
import { Campaign, FUNDING_MODEL_LABELS, formatRand, getPublic } from "@/lib/api";

type Update = { id: number; title: string; body: string; created_at: string; label: string };

type Props = { params: Promise<{ slug: string }> };

async function load(slug: string) {
  const data = await getPublic<{ campaign: Campaign }>(`/api/public/campaigns/${encodeURIComponent(slug)}`, 0);
  return data?.campaign ?? null;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const c = await load(slug);
  if (!c) return { title: "Campaign not found", robots: { index: false } };
  return {
    title: c.title,
    description: c.summary ?? undefined,
    alternates: { canonical: `/campaigns/${c.slug}` },
    openGraph: { title: c.title, description: c.summary ?? undefined, type: "article" },
  };
}

const CHECKS: [string, string][] = [
  ["campaign_reviewed", "Campaign reviewed by this platform"],
  ["email_verified", "Email verified"],
  ["identity_checked", "Identity checked"],
  ["business_documents_reviewed", "Business documents reviewed"],
  ["financial_information_verified", "Financial information independently verified"],
];

export default async function CampaignPage({ params }: Props) {
  const { slug } = await params;
  const c = await load(slug);
  if (!c) notFound();
  const updates = (await getPublic<{ updates: Update[] }>(`/api/public/campaigns/${encodeURIComponent(slug)}/updates`, 0))?.updates ?? [];
  const f = { ...c.funding, contributions_mode: c.funding.contributions_mode ?? "off" };

  return (
    <div className="container section stack">
      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <Link href="/">Home</Link> / <Link href="/discover">Discover</Link> / {c.title}
      </nav>
      <div className="row">
        {c.funding_model && <span className="badge">{FUNDING_MODEL_LABELS[c.funding_model]}</span>}
        {c.category && <span className="badge badge-warn">{c.category}</span>}
      </div>
      {c.cover_image_token && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={`/api/public/images/${c.cover_image_token}`}
          alt={`${c.title} cover`}
          style={{ width: "100%", maxHeight: 320, objectFit: "cover", borderRadius: 8, display: "block" }}
        />
      )}
      <h1>{c.title}</h1>
      <p className="lead muted">{c.summary}</p>

      <div className="grid-2">
        <div className="stack">
          <h2>About this project</h2>
          <p style={{ whiteSpace: "pre-wrap" }}>{c.description}</p>
          {c.transparency && (
            <section className="card stack" aria-labelledby="transparency">
              <h2 id="transparency">Transparency statement</h2>
              <p className="muted">{c.transparency.note}</p>
              {c.transparency.sections.map((s) => (
                <div key={s.key}>
                  <h3>{s.heading}</h3>
                  <p style={{ whiteSpace: "pre-wrap" }}>{s.body}</p>
                  <p className="muted" style={{ fontSize: "0.85rem" }}>
                    {s.source === "owner_entered" ? "Figures entered by the owner" : s.source === "owner_written" ? "Written by the owner" : s.source === "platform_status" ? "Current platform status" : "Standard platform statement"}
                  </p>
                </div>
              ))}
            </section>
          )}
          {c.objectives && (<><h3>Objectives</h3><p style={{ whiteSpace: "pre-wrap" }}>{c.objectives}</p></>)}
          {c.milestones.length > 0 && (
            <>
              <h2>Milestones</h2>
              <ol>
                {c.milestones.map((m, i) => (
                  <li key={i}><strong>{m.title}</strong>{m.target_date ? ` — target ${m.target_date}` : ""}
                    {m.detail && <div className="muted">{m.detail}</div>}</li>
                ))}
              </ol>
            </>
          )}
          {updates.length > 0 && (
            <>
              <h2>Updates</h2>
              {updates.map((u) => (
                <article key={u.id} className="card stack">
                  <h3>{u.title}</h3>
                  <p style={{ whiteSpace: "pre-wrap" }}>{u.body}</p>
                  <p className="muted" style={{ fontSize: "0.85rem" }}>{new Date(u.created_at).toLocaleDateString("en-ZA")} · {u.label}</p>
                </article>
              ))}
            </>
          )}
          <h2>How funds would be used</h2>
          <p className="muted">Planned by the campaign owner. Not independently verified.</p>
          <table>
            <thead><tr><th>Item</th><th>Amount</th></tr></thead>
            <tbody>
              {c.use_of_funds.map((u, i) => <tr key={i}><td>{u.item}</td><td>{formatRand(u.amount_cents)}</td></tr>)}
              <tr><th>Total</th><th>{formatRand(c.goal_cents)}</th></tr>
            </tbody>
          </table>
        </div>

        <aside className="stack">
          <div className="card stack">
            <h2>Funding goal</h2>
            <p style={{ fontSize: "1.8rem", margin: 0 }}><strong>{formatRand(c.goal_cents)}</strong></p>
            {/* Figures come only from confirmed, real payment records. The bar appears only when live money is confirmed. */}
            <dl style={{ margin: 0 }}>
              <dt className="muted">Confirmed contributions</dt><dd style={{ margin: 0 }}><strong>{formatRand(f.confirmed_raised_cents)}</strong></dd>
              {f.pending_cents > 0 && (<><dt className="muted">Pending (not yet confirmed)</dt><dd style={{ margin: 0 }}>{formatRand(f.pending_cents)}</dd></>)}
              {f.refunded_cents > 0 && (<><dt className="muted">Refunded</dt><dd style={{ margin: 0 }}>{formatRand(f.refunded_cents)}</dd></>)}
              {f.cancelled_or_failed_cents > 0 && (<><dt className="muted">Failed or cancelled</dt><dd style={{ margin: 0 }}>{formatRand(f.cancelled_or_failed_cents)}</dd></>)}
            </dl>
            {f.contributions_mode === "live" && f.confirmed_raised_cents > 0 && c.goal_cents ? (
              <div className="meter" role="img" aria-label={`${Math.min(100, Math.round((f.confirmed_raised_cents / c.goal_cents) * 100))}% of goal confirmed`}>
                <span style={{ width: `${Math.min(100, (f.confirmed_raised_cents / c.goal_cents) * 100)}%` }} />
              </div>
            ) : null}
            {f.contributions_mode === "off" ? (
              <p className="alert alert-info">Contributions are not open yet.</p>
            ) : (
              <ContributeBox slug={c.slug} mode={f.contributions_mode} />
            )}
            <FollowButton slug={c.slug} />
          </div>
          <div className="card stack">
            <h3>Review status</h3>
            <ul style={{ paddingLeft: 18, margin: 0 }}>
              {CHECKS.map(([k, label]) => (
                <li key={k}>{c.verification[k] ? "✓" : "✗"} {label}</li>
              ))}
            </ul>
            <p className="muted" style={{ fontSize: "0.88rem" }}>
              Each item is shown separately. Review of a campaign does not confirm that every claim is true.
            </p>
          </div>
          <div className="card stack">
            <h3>About the business</h3>
            <div className="row" style={{ alignItems: "center", gap: "0.75rem" }}>
              {(c.business as { logo_image_token?: string | null }).logo_image_token && (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={`/api/public/images/${(c.business as { logo_image_token?: string | null }).logo_image_token}`}
                  alt={`${c.business.name} logo`}
                  style={{ width: 48, height: 48, borderRadius: 6, objectFit: "cover", border: "1px solid var(--border, #e0e0e0)", flexShrink: 0 }}
                />
              )}
              <div>
                <p style={{ margin: 0 }}><Link href={`/businesses/${c.business.slug}`}>{c.business.name}</Link>{c.business.industry ? ` · ${c.business.industry}` : ""}</p>
                {c.location && <p className="muted" style={{ margin: 0 }}>{c.location}</p>}
              </div>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
