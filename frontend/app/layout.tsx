import type { Metadata } from "next";
import Link from "next/link";
import AuthNav from "@/components/AuthNav";
import "./globals.css";

const SITE = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

export const metadata: Metadata = {
  metadataBase: new URL(SITE),
  title: { default: "Sequence Crowdfunding — fund and present your project", template: "%s | Sequence Crowdfunding" },
  description:
    "A South African crowdfunding platform with tools to prepare your pitch deck, plan your finances and present your project clearly to supporters.",
  openGraph: { type: "website", locale: "en_ZA", siteName: "Sequence Crowdfunding" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-ZA">
      <body>
        <a className="skip-link" href="#main">Skip to content</a>
        <header className="site-header">
          <div className="container">
            <Link href="/" className="brand">Sequence Crowdfunding</Link>
            <nav className="nav" aria-label="Main">
              <Link href="/discover">Discover</Link>
              <Link href="/resources/pitch-deck-guide">Pitch-deck guide</Link>
              <AuthNav />
            </nav>
          </div>
        </header>
        <main id="main">{children}</main>
        <footer className="site-footer">
          <div className="container stack">
            <p>
              Sequence Industries (Pty) Ltd. Crowdfunding involves risk. Campaigns are created by their owners;
              a review by this platform does not guarantee that a project will succeed, deliver, or that any
              claim has been independently verified.
            </p>
            <p>This platform does not offer investments, shares or financial returns.</p>
            <p><a href="/terms">Terms (draft)</a> · <a href="/privacy">Privacy (draft)</a> · <a href="/risk">Risk disclosure (draft)</a></p>
          </div>
        </footer>
      </body>
    </html>
  );
}
