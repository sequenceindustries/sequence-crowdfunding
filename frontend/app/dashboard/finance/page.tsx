"use client";
import { useState } from "react";
import { api, formatRand } from "@/lib/api";

type Row = { month: number; revenue_cents: number; costs_cents: number; net_cents: number; closing_cash_cents: number };
type Scenario = { months: Row[]; first_month_cash_negative: number | null; first_month_net_non_negative: number | null };
type Result = {
  calculation_period: string; opening_cash_cents: number; formulas: Record<string, string>; warnings: string[];
  disclaimers: string[]; scenarios: Record<string, Scenario>;
};
type Line = { item: string; rand: string };

const toCents = (v: string) => Math.round(parseFloat(v || "0") * 100);
const lines = (ls: Line[]) => ls.filter((l) => l.item.trim()).map((l) => ({ item: l.item.trim(), amount_cents: toCents(l.rand) }));

function LineEditor({ label, value, onChange }: { label: string; value: Line[]; onChange: (v: Line[]) => void }) {
  return (
    <fieldset className="field" style={{ border: 0, padding: 0 }}>
      <legend style={{ fontWeight: 600 }}>{label}</legend>
      {value.map((l, i) => (
        <div className="row" key={i}>
          <input aria-label={`${label} item ${i + 1}`} placeholder="Item" value={l.item} style={{ flex: "2 1 180px" }} onChange={(e) => onChange(value.map((x, j) => (j === i ? { ...x, item: e.target.value } : x)))} />
          <input aria-label={`${label} amount ${i + 1} in rand`} placeholder="Amount (R)" type="number" min="0" value={l.rand} style={{ flex: "1 1 120px" }} onChange={(e) => onChange(value.map((x, j) => (j === i ? { ...x, rand: e.target.value } : x)))} />
        </div>
      ))}
      <button type="button" className="btn btn-secondary" onClick={() => onChange([...value, { item: "", rand: "" }])}>Add line</button>
    </fieldset>
  );
}

export default function Finance() {
  const [startup, setStartup] = useState<Line[]>([{ item: "", rand: "" }]);
  const [costs, setCosts] = useState<Line[]>([{ item: "", rand: "" }]);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    const f = new FormData(e.currentTarget);
    const pct = (k: string) => (f.get(k) ? Number(f.get(k)) : null);
    const scenarios: Record<string, { revenue_pct: number; cost_pct: number }> = {};
    for (const s of ["low", "high"]) if (pct(`${s}_rev`) !== null && pct(`${s}_cost`) !== null) scenarios[s] = { revenue_pct: pct(`${s}_rev`)!, cost_pct: pct(`${s}_cost`)! };
    const r = await api<Result & { message?: string }>("/finance/projection", {
      body: {
        funding_cents: toCents(String(f.get("funding"))), existing_cash_cents: toCents(String(f.get("existing"))),
        startup_costs: lines(startup), monthly_costs: lines(costs), monthly_revenue_cents: toCents(String(f.get("revenue"))),
        revenue_growth_bps: Math.round(parseFloat(String(f.get("growth") || "0")) * 100), months: Number(f.get("months") || 12),
        scenarios,
      },
    });
    if (!r.ok) { setResult(null); return setError(r.data?.message ?? "Check your inputs."); }
    setResult(r.data);
  }

  return (
    <div className="container section stack" style={{ maxWidth: 860 }}>
      <h1>Financial planner</h1>
      <p className="muted">Enter your own assumptions. Every figure below is calculated from them, nothing is filled in for you, and nothing you enter is stored.</p>
      {error && <div className="alert alert-error" role="alert">{error}</div>}
      <form onSubmit={run} className="card">
        <div className="grid-2">
          <div className="field"><label htmlFor="funding">Funding you expect to receive (R)</label><input id="funding" name="funding" type="number" min="0" /></div>
          <div className="field"><label htmlFor="existing">Cash you already have (R)</label><input id="existing" name="existing" type="number" min="0" /></div>
          <div className="field"><label htmlFor="revenue">Revenue in month 1 (R)</label><input id="revenue" name="revenue" type="number" min="0" /></div>
          <div className="field"><label htmlFor="growth">Monthly revenue growth (%)</label><input id="growth" name="growth" type="number" min="0" max="100" step="0.1" /></div>
          <div className="field"><label htmlFor="months">Months to project (1–60)</label><input id="months" name="months" type="number" min="1" max="60" defaultValue={12} /></div>
        </div>
        <LineEditor label="One-off startup costs" value={startup} onChange={setStartup} />
        <LineEditor label="Monthly costs" value={costs} onChange={setCosts} />
        <fieldset className="field" style={{ border: 0, padding: 0 }}>
          <legend style={{ fontWeight: 600 }}>Optional scenarios (your own percentages of the base case)</legend>
          <div className="row">
            <input aria-label="Low scenario revenue percent" name="low_rev" type="number" min="0" placeholder="Low: revenue %" style={{ width: 170 }} />
            <input aria-label="Low scenario cost percent" name="low_cost" type="number" min="0" placeholder="Low: costs %" style={{ width: 170 }} />
            <input aria-label="High scenario revenue percent" name="high_rev" type="number" min="0" placeholder="High: revenue %" style={{ width: 170 }} />
            <input aria-label="High scenario cost percent" name="high_cost" type="number" min="0" placeholder="High: costs %" style={{ width: 170 }} />
          </div>
        </fieldset>
        <button className="btn" type="submit">Calculate</button>
      </form>

      {result && (
        <section className="card stack" aria-live="polite">
          <h2>Results ({result.calculation_period})</h2>
          <p>Opening cash: <strong>{formatRand(result.opening_cash_cents)}</strong></p>
          {result.warnings.map((w) => <p key={w} className="alert alert-warn">{w}</p>)}
          {Object.entries(result.scenarios).map(([name, sc]) => (
            <div key={name} className="stack">
              <h3 style={{ textTransform: "capitalize" }}>{name} case</h3>
              <p className="muted">
                {sc.first_month_cash_negative ? `Cash runs out in month ${sc.first_month_cash_negative}.` : "Cash stays positive in this period."}{" "}
                {sc.first_month_net_non_negative ? `Monthly net is non-negative from month ${sc.first_month_net_non_negative}.` : "Monthly net stays negative."}
              </p>
              <div style={{ overflowX: "auto" }}>
                <table>
                  <thead><tr><th>Month</th><th>Revenue</th><th>Costs</th><th>Net</th><th>Closing cash</th></tr></thead>
                  <tbody>{sc.months.map((m) => (
                    <tr key={m.month}><td>{m.month}</td><td>{formatRand(m.revenue_cents)}</td><td>{formatRand(m.costs_cents)}</td><td>{formatRand(m.net_cents)}</td><td>{formatRand(m.closing_cash_cents)}</td></tr>
                  ))}</tbody>
                </table>
              </div>
            </div>
          ))}
          <h3>How it is calculated</h3>
          <ul>{Object.entries(result.formulas).map(([k, v]) => <li key={k}><code>{k}</code>: {v}</li>)}</ul>
          {result.disclaimers.map((d) => <p key={d} className="muted">{d}</p>)}
        </section>
      )}
    </div>
  );
}
