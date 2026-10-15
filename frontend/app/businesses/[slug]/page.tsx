import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Business, getPublic } from "@/lib/api";

type Props = { params: Promise<{ slug: string }> };

async function load(slug: string) {
  const d = await getPublic<{ profile: Business }>(`/api/public/businesses/${encodeURIComponent(slug)}`, 0);
  return d?.profile ?? null;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const p = await load((await params).slug);
  if (!p) return { title: "Business not found", robots: { index: false } };
  return { title: p.name, description: p.description?.slice(0, 155) ?? undefined, alternates: { canonical: `/businesses/${p.slug}` } };
}

const SECTIONS: [string, string][] = [
  ["description", "About"], ["problem", "The problem"], ["solution", "The solution"],
  ["target_customers", "Who it serves"], ["business_model", "Business model"], ["competitive_advantage", "Competitive advantage"],
];

export default async function BusinessPage({ params }: Props) {
  const p = await load((await params).slug);
  if (!p) notFound();
  return (
    <div className="container section stack">
      <nav className="breadcrumbs" aria-label="Breadcrumb"><Link href="/">Home</Link> / {p.name}</nav>
      <div className="row" style={{ alignItems: "center", gap: "1rem" }}>
        {p.logo_image_token && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={`/api/public/images/${p.logo_image_token}`}
            alt={`${p.name} logo`}
            style={{ width: 72, height: 72, borderRadius: 8, objectFit: "cover", border: "1px solid var(--border, #e0e0e0)", flexShrink: 0 }}
          />
        )}
        <div>
          <h1 style={{ margin: 0 }}>{p.name}</h1>
          <p className="muted" style={{ margin: 0 }}>{[p.industry, p.city, p.province, p.country].filter(Boolean).join(" · ")}</p>
        </div>
      </div>
      {SECTIONS.map(([k, label]) => p[k] ? <section key={k}><h2>{label}</h2><p style={{ whiteSpace: "pre-wrap" }}>{p[k]}</p></section> : null)}
      {p.website && <p><a href={p.website} rel="noopener nofollow ugc">Website</a></p>}
      {p.contact_email && <p>Contact: {p.contact_email}</p>}
    </div>
  );
}
