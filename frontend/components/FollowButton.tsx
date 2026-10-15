"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function FollowButton({ slug }: { slug: string }) {
  const [following, setFollowing] = useState<boolean | null>(null);
  const [signedOut, setSignedOut] = useState(false);

  useEffect(() => {
    let alive = true;
    api<{ campaigns?: { slug: string }[] }>("/follows/mine").then((r) => {
      if (!alive) return;
      if (r.status === 401) return setSignedOut(true);
      setFollowing((r.data?.campaigns ?? []).some((c) => c.slug === slug));
    });
    return () => { alive = false; };
  }, [slug]);

  if (signedOut) return <a className="btn btn-secondary" href="/login">Log in to follow</a>;
  if (following === null) return null;
  return (
    <button className="btn btn-secondary" aria-pressed={following} onClick={async () => {
      const r = await api(`/campaigns/${slug}/follow`, { method: following ? "DELETE" : "POST", body: following ? undefined : {} });
      if (r.ok) setFollowing(!following);
    }}>
      {following ? "Following ✓" : "Follow this campaign"}
    </button>
  );
}
