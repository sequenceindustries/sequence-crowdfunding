import type { Metadata } from "next";
import Link from "next/link";
import CampaignCard from "@/components/CampaignCard";
import { Campaign, FUNDING_MODEL_LABELS, getPublic } from "@/lib/api";

export const metadata: Metadata = {
  title: "Discover crowdfunding campaigns in South Africa",
  description: "Browse reviewed crowdfunding campaigns from South African founders and community projects.",
  alternates: { canonical: "/discover" },
};

type Search = { [k: string]: string | string[] | undefined };

export default async function Discover({ searchParams }: { searchParams: Promise<Search> }) {
  const sp = await searchParams;
  const one = (k: string) => (typeof sp[k] === "string" ? (sp[k] as string) : "");
  const qs = new URLSearchParams();
  for (const k of ["q", "funding_model", "category", "stage", "sort", "page"]) if (one(k)) qs.set(k, one(k));
  const data = await getPublic<{ campaigns: Campaign[]; total: number; page: number; per_page: number }>(
    `/api/public/campaigns?${qs.toString()}`,
  );
  const cats = (await getPublic<{ categories: { category: string; count: number }[] }>("/api/public/categories"))?.categories ?? [];
  const page = data?.page ?? 1;
  const pages = data ? Math.max(1, Math.ceil(data.total / data.per_page)) : 1;
  const link = (p: number) => {
    const n = new URLSearchParams(qs);
    n.set("page", String(p));
    return `/discover?${n.toString()}`;
  };

  return (
    <div className="container section stack">
      <nav className="breadcrumbs" aria-label="Breadcrumb"><Link href="/">Home</Link> / Discover</nav>
      <h1>Discover campaigns</h1>
      <form id="search-form" className="card row" role="search">
        <div className="field" style={{ flex: "2 1 220px", margin: 0 }}>
          <label htmlFor="q">Search</label>
          <input id="q" name="q" defaultValue={one("q")} placeholder="e.g. solar Soweto, bakery, tutoring" />
        </div>
        <div className="field" style={{ flex: "1 1 180px", margin: 0 }}>
          <label htmlFor="funding_model">Funding model</label>
          <select id="funding_model" name="funding_model" defaultValue={one("funding_model")}>
            <option value="">Any</option>
            {Object.entries(FUNDING_MODEL_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        <div className="field" style={{ flex: "1 1 160px", margin: 0 }}>
          <label htmlFor="sort">Sort</label>
          <select id="sort" name="sort" defaultValue={one("sort")}>
            <option value="">{one("q") ? "Best match" : "Most recent"}</option>
            <option value="recent">Most recent</option>
            <option value="title">Title A–Z</option>
            <option value="goal_asc">Smallest goal first</option>
            <option value="goal_desc">Largest goal first</option>
          </select>
        </div>
        <button className="btn" type="submit">Apply</button>
      </form>

      {cats.length > 0 && (
        <nav className="row" aria-label="Categories">
          <Link className={`badge ${one("category") ? "" : "badge-warn"}`} href="/discover">All</Link>
          {cats.map((c) => (
            <Link key={c.category} className={`badge ${one("category") === c.category ? "badge-warn" : ""}`}
              href={`/discover?category=${encodeURIComponent(c.category)}`}>{c.category} ({c.count})</Link>
          ))}
        </nav>
      )}
      {one("category") && <input form="search-form" type="hidden" name="category" value={one("category")} />}

      {!data ? (
        <div className="alert alert-error">Campaigns could not be loaded right now. Please try again shortly.</div>
      ) : data.campaigns.length === 0 ? (
        <div className="empty"><p><strong>No campaigns match.</strong></p><p>Try a different search or clear the filters.</p></div>
      ) : (
        <>
          <p className="muted">{data.total} campaign{data.total === 1 ? "" : "s"}</p>
          <div className="grid">{data.campaigns.map((c) => <CampaignCard key={c.id} c={c} />)}</div>
          <nav className="row" aria-label="Pagination">
            {page > 1 && <Link className="btn btn-secondary" href={link(page - 1)}>Previous</Link>}
            <span className="muted">Page {page} of {pages}</span>
            {page < pages && <Link className="btn btn-secondary" href={link(page + 1)}>Next</Link>}
          </nav>
        </>
      )}
    </div>
  );
}
