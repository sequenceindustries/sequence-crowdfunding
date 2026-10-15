export const API_URL = process.env.API_URL ?? "http://localhost:5000";

export type Campaign = {
  id: number;
  slug: string;
  title: string;
  category: string | null;
  summary: string | null;
  description: string | null;
  location: string | null;
  stage: string | null;
  objectives: string | null;
  funding_model: string | null;
  currency: string;
  goal_cents: number | null;
  duration_days: number | null;
  funding_purpose: string | null;
  use_of_funds: { item: string; amount_cents: number }[];
  status: string;
  published_at: string | null;
  milestones: { title: string; detail: string | null; target_date: string | null }[];
  business: { slug: string; name: string; industry: string | null; logo_image_token?: string | null };
  funding: {
    confirmed_raised_cents: number;
    pending_cents: number;
    refunded_cents: number;
    cancelled_or_failed_cents: number;
    pledged_cents: number;
    contributions_mode: "off" | "simulated" | "live";
  };
  verification: Record<string, boolean>;
  transparency?: {
    approved_at: string;
    note: string;
    sections: { key: string; heading: string; body: string; source: string }[];
  } | null;
  review_note?: string | null;
  match?: { terms: string[]; fields: string[] };
  cover_image_token?: string | null;
};

export type Business = Record<string, string | null> & { slug: string; name: string; logo_image_token?: string | null };

/** Server-side read of public data. Returns null on failure so pages degrade honestly.
 *  `revalidate` is in seconds; 0 means never cached. Anything about money, suspension or privacy
 *  (campaign pages, updates, business profiles) must pass 0 so a change takes effect immediately. */
export async function getPublic<T>(path: string, revalidate = 30): Promise<T | null> {
  try {
    const res = await fetch(`${API_URL}${path}`, revalidate === 0 ? { cache: "no-store" } : { next: { revalidate } });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export function formatRand(cents: number | null | undefined): string {
  if (cents == null) return "Not set";
  return new Intl.NumberFormat("en-ZA", { style: "currency", currency: "ZAR", maximumFractionDigits: 0 }).format(
    cents / 100,
  );
}

export const FUNDING_MODEL_LABELS: Record<string, string> = {
  donation: "Donation",
  reward: "Reward",
  business_support: "Business support",
};

/** Browser-side client that carries the CSRF token returned at login. */
let csrfToken: string | null = null;

/** Returns the current CSRF token so components that issue raw fetch calls can include it. */
export function getCsrf(): string | null { return csrfToken; }

export async function api<T = unknown>(
  path: string,
  options: { method?: string; body?: unknown; form?: FormData; headers?: Record<string, string> } = {},
): Promise<{ ok: boolean; status: number; data: T }> {
  const headers: Record<string, string> = { ...(options.headers ?? {}) };
  if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(`/api${path}`, {
    method: options.method ?? (options.body !== undefined || options.form ? "POST" : "GET"),
    headers,
    body: options.form ?? (options.body !== undefined ? JSON.stringify(options.body) : undefined),
    credentials: "same-origin",
  });
  let data: unknown = null;
  try {
    data = await res.json();
  } catch {}
  const token = (data as { csrf_token?: string } | null)?.csrf_token;
  if (token) csrfToken = token;
  return { ok: res.ok, status: res.status, data: data as T };
}
