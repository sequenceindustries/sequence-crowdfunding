import type { Metadata } from "next";

export const metadata: Metadata = { title: "Privacy notice (draft)", alternates: { canonical: "/privacy" } };

export default function Privacy() {
  return (
    <div className="container section stack" style={{ maxWidth: 760 }}>
      <h1>Privacy notice</h1>
      <p className="alert alert-warn">Working draft. It has not been reviewed by a lawyer, and the platform does not yet claim compliance with POPIA. It states what the software does today.</p>
      <h2>What we store</h2>
      <p>Your account details, business profiles and campaigns, documents you upload, and a record of important actions (such as logins to staff areas, reviewer decisions and document downloads).</p>
      <h2>Uploaded documents</h2>
      <p>Pitch decks are visible only to you, and to platform reviewers while a linked campaign is under review. Verification documents are visible only to reviewers, and each time one is opened it is logged. They are never public and are not sent to any outside AI service.</p>
      <h2>AI features</h2>
      <p>The current analysis and drafting tools run on the platform&apos;s own servers using fixed rules. If an outside AI provider is ever added, your text will be sent to it only after you are told who receives it and you agree.</p>
      <h2>Your choices</h2>
      <p>You can delete your account from the platform. Self-service correction and data export are not yet available, and a formal access process and an Information Officer have not yet been set up.</p>
      <h2>Email</h2>
      <p>We send account emails (confirmation, password reset, review decisions). Nothing is sent to third parties for marketing.</p>
    </div>
  );
}
