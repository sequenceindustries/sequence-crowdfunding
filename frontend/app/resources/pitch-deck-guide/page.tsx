import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "How to prepare a pitch deck for crowdfunding",
  description: "The sections a clear pitch deck needs, common mistakes, and how to explain your use of funds honestly.",
  alternates: { canonical: "/resources/pitch-deck-guide" },
};

const SECTIONS = [
  ["Problem", "Say who has the problem, how often, and how you know. Evidence beats adjectives."],
  ["Solution", "Explain what you offer in plain language and why it solves that problem."],
  ["Market and customers", "Name your first customers. If you quote a market size, cite where it came from."],
  ["Business model", "Show how money comes in: what you charge, to whom, and how often."],
  ["Competition", "List real alternatives, including customers doing nothing, and how you differ."],
  ["Traction", "Share progress you can prove. If you are pre-launch, say so."],
  ["Team", "Show who is involved and what relevant experience they bring."],
  ["Funding request and use of funds", "State the amount and break it into line items that add up to it."],
  ["Risks", "Naming risks builds trust. Say what could go wrong and how you would respond."],
];

export default function Guide() {
  return (
    <div className="container section stack" style={{ maxWidth: 760 }}>
      <nav className="breadcrumbs" aria-label="Breadcrumb"><Link href="/">Home</Link> / Resources / Pitch-deck guide</nav>
      <h1>How to prepare a pitch deck for crowdfunding</h1>
      <p className="muted">
        A pitch deck is a short presentation that explains your project and why it deserves support. These are the
        sections most supporters look for.
      </p>
      {SECTIONS.map(([t, d]) => <section key={t}><h2>{t}</h2><p>{d}</p></section>)}
      <h2>Mistakes to avoid</h2>
      <ul>
        <li>Claims such as “the only” or “guaranteed” without evidence.</li>
        <li>A funding request that does not match the use-of-funds total.</li>
        <li>Revenue projections with no stated assumptions.</li>
        <li>Promising returns. Supporters are backing a project, not buying an investment.</li>
      </ul>
      <p><Link className="btn" href="/register">Check your own deck</Link></p>
    </div>
  );
}
