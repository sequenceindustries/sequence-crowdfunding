"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Campaign, api, formatRand } from "@/lib/api";

type Profile = { id: number; name: string; industry: string | null };
type Contribution = {
  id: number;
  amount_cents: number;
  status: string;
  created_at: string;
  campaign_title: string;
  campaign_slug: string;
};

async function fetchDashboard() {
  const me = await api<{ user: { role: string; email_verified: boolean } | null }>("/auth/me");
  const role = me.data?.user?.role ?? null;
  const verified = me.data?.user?.email_verified ?? false;
  let profiles: Profile[] = [];
  let campaigns: Campaign[] = [];
  let followed: Campaign[] = [];
  let contributions: Contribution[] = [];
  if (role === "founder") {
    const [p, c] = await Promise.all([
      api<{ profiles: Profile[] }>("/profiles/mine"),
      api<{ campaigns: Campaign[] }>("/campaigns/mine"),
    ]);
    profiles = p.data?.profiles ?? [];
    campaigns = c.data?.campaigns ?? [];
  } else if (role === "supporter") {
    const [f, c] = await Promise.all([
      api<{ campaigns: Campaign[] }>("/follows/mine"),
      api<{ contributions: Contribution[] }>("/contributions/mine"),
    ]);
    followed = f.data?.campaigns ?? [];
    contributions = c.data?.contributions ?? [];
  }
  return { role, verified, profiles, campaigns, followed, contributions };
}

export default function Dashboard() {
  const [role, setRole] = useState<string | null | undefined>(undefined);
  const [verified, setVerified] = useState(true);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [followed, setFollowed] = useState<Campaign[]>([]);
  const [contributions, setContributions] = useState<Contribution[]>([]);
  const [msg, setMsg] = useState<{ kind: "error" | "info"; text: string } | null>(null);

  const apply = useCallback((d: {
    role: string | null; verified: boolean; profiles: Profile[]; campaigns: Campaign[];
    followed: Campaign[]; contributions: Contribution[];
  }) => {
    setRole(d.role);
    setVerified(d.verified);
    setProfiles(d.profiles);
    setCampaigns(d.campaigns);
    setFollowed(d.followed);
    setContributions(d.contributions);
  }, []);

  const load = useCallback(async () => apply(await fetchDashboard()), [apply]);

  useEffect(() => {
    let alive = true;
    fetchDashboard().then((d) => { if (alive) apply(d); });
    return () => { alive = false; };
  }, [apply]);

  async function createProfile(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const r = await api("/profiles", { body: { name: f.get("name"), industry: f.get("industry") } });
    if (!r.ok) return setMsg({ kind: "error", text: "Could not create the profile. Check the name and try again." });
    (e.target as HTMLFormElement).reset();
    setMsg({ kind: "info", text: "Business profile created." });
    load();
  }

  async function act(c: Campaign, action: "submit" | "publish") {
    const r = await api<{ problems?: string[]; message?: string }>(`/campaigns/${c.id}/${action}`, { body: {} });
    if (!r.ok) {
      const detail = r.data?.problems?.join(" ") ?? r.data?.message ?? "That action is not available.";
      return setMsg({ kind: "error", text: detail });
    }
    setMsg({ kind: "info", text: action === "submit" ? "Submitted for review." : "Campaign published." });
    load();
  }

  if (role === undefined) return <div className="container section">Loading…</div>;
  if (role === null) return <div className="container section stack"><p>Please <Link href="/login">log in</Link> to see your dashboard.</p></div>;
  if (role === "admin" || role === "verification_reviewer")
    return <div className="container section stack"><h1>Dashboard</h1><p><Link className="btn" href="/staff">Open the review desk</Link></p></div>;
  if (role === "supporter") {
    return (
      <div className="container section stack">
        <h1>Your dashboard</h1>
        {msg && <div className={`alert ${msg.kind === "error" ? "alert-error" : "alert-info"}`} role="status">{msg.text}</div>}

        <section className="card stack">
          <h2>Campaigns you follow</h2>
          {followed.length === 0 ? (
            <p className="muted">
              You haven't followed any campaigns yet.{" "}
              <Link href="/discover">Browse campaigns</Link> to find ones you care about.
            </p>
          ) : (
            <table>
              <thead><tr><th>Campaign</th><th>Business</th><th>Goal</th><th>Raised</th><th></th></tr></thead>
              <tbody>
                {followed.map((c) => (
                  <tr key={c.id}>
                    <td>{c.title}</td>
                    <td>{c.business.name}</td>
                    <td>{c.goal_cents != null ? formatRand(c.goal_cents) : "—"}</td>
                    <td>{formatRand(c.funding.confirmed_raised_cents)}</td>
                    <td>
                      <Link className="btn btn-secondary" href={`/campaigns/${c.slug}`}>View</Link>{" "}
                      <button className="btn btn-secondary" onClick={async () => {
                        await api(`/campaigns/${c.slug}/follow`, { method: "DELETE" });
                        setFollowed((prev) => prev.filter((x) => x.id !== c.id));
                      }}>Unfollow</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="card stack">
          <h2>Contributions</h2>
          {contributions.length === 0 ? (
            <p className="muted">
              No contributions yet. Contributions will appear here once the platform accepts payments.
            </p>
          ) : (
            <table>
              <thead><tr><th>Campaign</th><th>Amount</th><th>Status</th><th>Date</th></tr></thead>
              <tbody>
                {contributions.map((p) => (
                  <tr key={p.id}>
                    <td><Link href={`/campaigns/${p.campaign_slug}`}>{p.campaign_title}</Link></td>
                    <td>{formatRand(p.amount_cents)}</td>
                    <td><span className="badge">{p.status}</span></td>
                    <td>{new Date(p.created_at).toLocaleDateString("en-ZA")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="muted" style={{ fontSize: "0.85rem" }}>
            Contributions on this platform are simulated. No real money has been transferred.
            {" "}Live payments will be enabled once the platform is licensed and approved.
          </p>
        </section>
      </div>
    );
  }

  if (role !== "founder")
    return <div className="container section stack"><h1>Dashboard</h1><p>Please <Link href="/login">log in</Link> to use the dashboard.</p></div>;

  return (
    <div className="container section stack">
      <h1>Your dashboard</h1>
      {!verified && (
        <div className="alert alert-warn" role="status">
          Confirm your email address to submit campaigns.{" "}
          <button className="btn btn-secondary" onClick={async () => {
            const r = await api("/auth/request-verification", { body: {} });
            setMsg(r.ok ? { kind: "info", text: "Confirmation email sent." } : { kind: "error", text: "Please wait before requesting another email." });
          }}>Resend email</button>
        </div>
      )}
      {msg && <div className={`alert ${msg.kind === "error" ? "alert-error" : "alert-info"}`} role="status">{msg.text}</div>}

      <section className="card stack">
        <h2>Business profiles</h2>
        {profiles.length === 0 ? <p className="muted">Create a profile first. Campaigns belong to a profile.</p> :
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {profiles.map((p) => (
              <li key={p.id} className="row" style={{ justifyContent: "space-between", alignItems: "center", padding: "0.25rem 0" }}>
                <span>{p.name}{p.industry ? ` · ${p.industry}` : ""}</span>
                <Link className="btn btn-secondary" href={`/dashboard/profiles/${p.id}/edit`}>Edit profile</Link>
              </li>
            ))}
          </ul>}
        <form onSubmit={createProfile} className="row" style={{ alignItems: "end" }}>
          <div className="field" style={{ margin: 0 }}><label htmlFor="name">Business name</label><input id="name" name="name" required /></div>
          <div className="field" style={{ margin: 0 }}><label htmlFor="industry">Industry</label><input id="industry" name="industry" /></div>
          <button className="btn" type="submit">Add profile</button>
        </form>
      </section>

      <section className="card stack">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h2 style={{ margin: 0 }}>Campaigns</h2>
          {profiles.length > 0 && <Link className="btn" href="/dashboard/campaigns/new">New campaign</Link>}
        </div>
        {campaigns.length === 0 ? <div className="empty">No campaigns yet. Drafts are saved so you can come back later.</div> : (
          <table>
            <thead><tr><th>Title</th><th>Goal</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {campaigns.map((c) => (
                <tr key={c.id}>
                  <td>{c.title}{c.review_note && <div className="muted">Reviewer note: {c.review_note}</div>}</td>
                  <td>{formatRand(c.goal_cents)}</td>
                  <td><span className="badge">{c.status.replace("_", " ")}</span></td>
                  <td>
                    {(c.status === "draft" || c.status === "changes_requested") && <Link className="btn btn-secondary" href={`/dashboard/campaigns/${c.id}/edit`}>Edit</Link>}{" "}
                    {(c.status === "draft" || c.status === "changes_requested") && <button className="btn btn-secondary" onClick={() => act(c, "submit")}>Submit for review</button>}
                    {c.status === "approved" && <button className="btn" onClick={() => act(c, "publish")}>Publish</button>}
                    {c.status === "published" && <Link className="btn btn-secondary" href={`/dashboard/campaigns/${c.id}/updates`}>Post update</Link>}
                    {" "}<Link className="btn btn-secondary" href={`/dashboard/campaigns/${c.id}/assistant`}>Improve &amp; transparency</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="card stack">
        <h2>Verification</h2>
        <p className="muted">Upload identity and business documents. They are stored privately, seen only by platform reviewers, and a badge appears on your campaign only after a person approves the document.</p>
        <div className="row"><Link className="btn btn-secondary" href="/dashboard/verification">Manage verification documents</Link></div>
      </section>

      <section className="card stack">
        <h2>Pitch-deck and finance tools</h2>
        <p className="muted">Check a deck you already have, build one from a questionnaire, or plan your finances.</p>
        <div className="row">
          <Link className="btn btn-secondary" href="/dashboard/pitch-decks">Check an existing deck</Link>
          <Link className="btn btn-secondary" href="/dashboard/deck-builder">Build a deck</Link>
          <Link className="btn btn-secondary" href="/dashboard/finance">Financial planner</Link>
        </div>
      </section>
    </div>
  );
}
