import Link from "next/link";
import CampaignCard from "@/components/CampaignCard";
import { Campaign, getPublic } from "@/lib/api";

type Stats = { published_campaigns: number; total_campaigns: number; founders: number; top_categories: { category: string; count: number }[] };

export default async function Home() {
  const [data, statsData, catData] = await Promise.all([
    getPublic<{ campaigns: Campaign[] }>("/api/public/campaigns?per_page=6"),
    getPublic<{ stats: Stats }>("/api/public/stats"),
    getPublic<{ categories: { category: string; count: number }[] }>("/api/public/categories"),
  ]);
  const campaigns = data?.campaigns ?? [];
  const stats = statsData?.stats;
  const categories = catData?.categories?.slice(0, 8) ?? [];

  return (
    <>
      <section className="hero">
        <div className="container stack">
          <h1>Present your project clearly. Raise support honestly.</h1>
          <p className="lead">
            Sequence Crowdfunding helps South African founders and community projects prepare a strong pitch,
            explain how funds will be used, and share it with supporters.
          </p>
          <form action="/discover" className="search" role="search">
            <label htmlFor="q" className="sr-only">Search campaigns</label>
            <input id="q" name="q" type="search" placeholder="Search campaigns, e.g. solar, bakery, school" />
            <button className="btn" type="submit">Search</button>
          </form>
          <div className="row">
            <Link className="btn" href="/register">Start a campaign</Link>
            <Link className="btn btn-secondary" href="/discover">Browse campaigns</Link>
          </div>
        </div>
      </section>

      {stats && (stats.published_campaigns > 0 || stats.founders > 0) && (
        <section className="section" style={{ paddingTop: "1.5rem", paddingBottom: "1.5rem" }}>
          <div className="container">
            <div className="row" style={{ justifyContent: "center", gap: "2rem", flexWrap: "wrap" }}>
              {stats.published_campaigns > 0 && (
                <div style={{ textAlign: "center" }}>
                  <div style={{ fontSize: "2rem", fontWeight: 700, lineHeight: 1 }}>{stats.published_campaigns}</div>
                  <div className="muted" style={{ fontSize: "0.9rem" }}>Published campaign{stats.published_campaigns !== 1 ? "s" : ""}</div>
                </div>
              )}
              {stats.founders > 0 && (
                <div style={{ textAlign: "center" }}>
                  <div style={{ fontSize: "2rem", fontWeight: 700, lineHeight: 1 }}>{stats.founders}</div>
                  <div className="muted" style={{ fontSize: "0.9rem" }}>Founder{stats.founders !== 1 ? "s" : ""} registered</div>
                </div>
              )}
              {stats.total_campaigns > stats.published_campaigns && stats.total_campaigns > 0 && (
                <div style={{ textAlign: "center" }}>
                  <div style={{ fontSize: "2rem", fontWeight: 700, lineHeight: 1 }}>{stats.total_campaigns}</div>
                  <div className="muted" style={{ fontSize: "0.9rem" }}>Campaigns in progress</div>
                </div>
              )}
            </div>
          </div>
        </section>
      )}

      {categories.length > 0 && (
        <section className="section" style={{ paddingTop: "1rem", paddingBottom: "1.5rem" }}>
          <div className="container stack">
            <h2>Browse by category</h2>
            <div className="row" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
              {categories.map((cat) => (
                <Link
                  key={cat.category}
                  href={`/discover?category=${encodeURIComponent(cat.category)}`}
                  className="badge badge-warn"
                  style={{ textDecoration: "none", padding: "0.35rem 0.75rem", fontSize: "0.9rem" }}
                >
                  {cat.category} ({cat.count})
                </Link>
              ))}
              <Link href="/discover" className="badge" style={{ textDecoration: "none", padding: "0.35rem 0.75rem", fontSize: "0.9rem" }}>
                All campaigns →
              </Link>
            </div>
          </div>
        </section>
      )}

      <section className="section">
        <div className="container stack">
          <h2>Recently published campaigns</h2>
          {campaigns.length === 0 ? (
            <div className="empty">
              <p><strong>No campaigns are published yet.</strong></p>
              <p>Every campaign is reviewed before it appears here. Be among the first founders to submit one.</p>
              <Link className="btn" href="/register">Start a campaign</Link>
            </div>
          ) : (
            <>
              <div className="grid">{campaigns.map((c) => <CampaignCard key={c.id} c={c} />)}</div>
              <div style={{ textAlign: "center" }}>
                <Link className="btn btn-secondary" href="/discover">See all campaigns</Link>
              </div>
            </>
          )}
        </div>
      </section>

      <section className="section">
        <div className="container stack">
          <h2>How it works</h2>
          <ol className="steps">
            <li><h3>Build your profile</h3><p className="muted">Describe your business, the problem you solve and who you serve. You choose what is public.</p></li>
            <li><h3>Prepare your pitch</h3><p className="muted">Upload your pitch deck for a completeness check that shows what is missing or unclear.</p></li>
            <li><h3>Submit for review</h3><p className="muted">A person reviews every campaign before it is published. Changes may be requested.</p></li>
            <li><h3>Share with supporters</h3><p className="muted">Approved campaigns are listed publicly with a clear breakdown of how funds would be used.</p></li>
          </ol>
        </div>
      </section>

      <section className="section">
        <div className="container grid-2">
          <div className="card stack">
            <h2>Pitch-deck tools</h2>
            <p>
              Upload a PDF or PowerPoint deck and get a structured report on which sections are covered, which are
              thin, and which claims need evidence. The score measures completeness only. It is not a prediction
              of fundraising success, and it does not verify that anything in the deck is true.
            </p>
            <Link href="/resources/pitch-deck-guide">Read the pitch-deck guide</Link>
          </div>
          <div className="card stack">
            <h2>Transparent by design</h2>
            <p>
              We only show money as raised when it is confirmed by a payment record. Review status is shown
              item by item, so a reviewed campaign is never presented as fully verified.
            </p>
            <p className="alert alert-info">
              Contributions are not open yet. Campaigns can be prepared and reviewed now.
            </p>
          </div>
        </div>
      </section>
    </>
  );
}
