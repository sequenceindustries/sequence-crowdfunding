import type { MetadataRoute } from "next";
import { Campaign, getPublic } from "@/lib/api";

const SITE = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  // Only published campaigns are ever returned by this endpoint.
  const data = await getPublic<{ campaigns: Campaign[] }>("/api/public/campaigns?per_page=50");
  const campaigns = (data?.campaigns ?? []).map((c) => ({
    url: `${SITE}/campaigns/${c.slug}`,
    lastModified: c.published_at ?? undefined,
  }));
  return [
    { url: SITE },
    { url: `${SITE}/discover` },
    { url: `${SITE}/resources/pitch-deck-guide` },
    { url: `${SITE}/terms` },
    { url: `${SITE}/privacy` },
    { url: `${SITE}/risk` },
    ...campaigns,
  ];
}
