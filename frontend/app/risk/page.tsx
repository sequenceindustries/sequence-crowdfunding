import type { Metadata } from "next";

export const metadata: Metadata = { title: "Risk disclosure (draft)", alternates: { canonical: "/risk" } };

export default function Risk() {
  return (
    <div className="container section stack" style={{ maxWidth: 760 }}>
      <h1>Risk disclosure</h1>
      <p className="alert alert-warn">Working draft, not yet reviewed by a lawyer.</p>
      <ul>
        <li>Campaigns are created by their owners. The platform does not guarantee that any project will succeed, deliver, or use funds as described.</li>
        <li>You could lose everything you contribute. Contributions are not investments and are not protected by any deposit or investor-compensation scheme.</li>
        <li>Figures in a campaign are entered by the owner and are not independently verified unless the page says so for that item.</li>
        <li>A review by the platform checks completeness and obvious problems. It is not an audit or an endorsement.</li>
        <li>Only contribute an amount you can afford to lose, and ask the owner questions before you do.</li>
      </ul>
    </div>
  );
}
