import Link from "next/link";
import { Campaign, FUNDING_MODEL_LABELS, formatRand } from "@/lib/api";

export default function CampaignCard({ c }: { c: Campaign }) {
  return (
    <article className="card stack">
      {c.cover_image_token && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={`/api/public/images/${c.cover_image_token}`}
          alt={`${c.title} cover`}
          style={{ width: "100%", height: 180, objectFit: "cover", borderRadius: 6, display: "block" }}
        />
      )}
      <div className="row">
        {c.funding_model && <span className="badge">{FUNDING_MODEL_LABELS[c.funding_model] ?? c.funding_model}</span>}
        {c.category && <span className="badge badge-warn">{c.category}</span>}
      </div>
      <h3><Link href={`/campaigns/${c.slug}`}>{c.title}</Link></h3>
      <p className="muted">{c.summary}</p>
      <p>
        <strong>Goal: {formatRand(c.goal_cents)}</strong>
        <br />
        <span className="muted">by {c.business.name}</span>
      </p>
      {c.match && c.match.fields.length > 0 && (
        <p className="muted" style={{ fontSize: "0.85rem" }}>Matched your search in: {c.match.fields.join(", ")}</p>
      )}
    </article>
  );
}
