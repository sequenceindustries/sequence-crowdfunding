# Open legal, commercial and technical questions (none resolved)

## Commercial
- **Provisional:** the R500 fee is set to buy analysis plus improvement report for one deck ("package"). Change `PITCH_DECK_FEE_SERVICE` if the business means something else. Refund rules for the fee and VAT treatment are undecided. Charging stays off.

## Legal (for qualified counsel before any real transactions)
- Whether holding or routing contributions needs specific licensing or a trust/escrow structure.
- Financial-sector and securities rules before any investment model; consumer-protection and electronic-transactions obligations; tax treatment; charity and fundraising rules for donation campaigns, especially medical or emergency ones.
- AML/KYC obligations and what identity verification is justified.
- POPIA: lawful basis, retention periods, operator agreements, cross-border transfer if an overseas AI provider is used, and a formal access/correction process. A deletion endpoint exists; correction and export do not.

## Payments
- No provider selected or approved. Crowdfunding underwriting and settlement terms are unknown.

## AI provider
- None chosen. Cost limits, data-processing terms and consent wording are needed before sending decks to an external service.

## Not yet built
A real email provider (the dev outbox only stores mail), a real payment provider adapter (only the mock exists), notifications to followers, saved preferences and personalised matching (discovery is plain keyword search), supporter dashboard, campaign editing UI with milestones, image uploads, a job queue, S3-compatible storage, frontend automated tests, and deployment to Railway.

## Built, with known limits
- **Pitch-deck generator**: arranges the founder's own words into slides; it does not rewrite or expand them, so slide quality equals answer quality. An AI rewriting step would need the consent and cost controls above. Editing a slide by hand re-checks only that it is non-empty, not whether its figures still add up.
- **Financial planner**: flat monthly costs, compounding growth, no tax, VAT, seasonality or debt service. Scenario percentages are the founder's own. Nothing entered is stored.

- **Verification**: approved documents do not expire and there is no re-check schedule. Whether a reviewer needs a second sign-off for identity documents, and how long evidence is retained after a campaign ends, are undecided. `financial_information_verified` is never set by any workflow: bank confirmations are reviewed but do not verify finances. Approved documents cannot be deleted by the owner (kept for the record); a removal process is needed for POPIA.
- **Campaign/transparency assistants** are rule-based (fixed checks and templates), not an LLM. The wording of the fixed platform statements needs legal review. Campaign lists run one extra query per card for the transparency lookup; cache or join it if lists grow.
- **Frontend**: pages were click-tested once in a headless browser; there are no automated frontend tests. Terms, privacy and risk pages are drafts.
