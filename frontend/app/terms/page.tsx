import type { Metadata } from "next";

export const metadata: Metadata = { title: "Terms of use (draft)", alternates: { canonical: "/terms" } };

export default function Terms() {
  return (
    <div className="container section stack" style={{ maxWidth: 760 }}>
      <h1>Terms of use</h1>
      <p className="alert alert-warn">Working draft. These terms have not been reviewed by a lawyer and are not yet in force. They describe how the platform currently behaves.</p>
      <h2>What the platform is</h2>
      <p>Sequence Industries (Pty) Ltd provides a place where business owners publish campaigns and supporters can follow them. Campaigns are written by their owners. The platform does not offer investments, shares, loans or financial returns.</p>
      <h2>Contributions</h2>
      <p>Contributions are not yet switched on. When they are, a contribution is a donation, a pre-purchase or support for a business, depending on the campaign, and is never an investment. A contribution does not give ownership, profit share or repayment. Refund rules have not yet been finalised and will be set out here before any real payment is accepted.</p>
      <h2>Review is not verification</h2>
      <p>A campaign marked as reviewed has been read by a person against the platform&apos;s checklist. This does not confirm that claims are true, that the business will deliver, or that figures are accurate. Each verification badge on a campaign says exactly what was checked.</p>
      <h2>Your responsibilities as a campaign owner</h2>
      <p>You must give accurate information, must not promise returns or remove risk from your wording, and must report progress honestly. Campaigns that mislead can be suspended, with a recorded reason.</p>
      <h2>Fees</h2>
      <p>No fee is charged at present. Any fee, including the pitch-deck service fee, will show its exact amount and what it buys before you are charged.</p>
    </div>
  );
}
