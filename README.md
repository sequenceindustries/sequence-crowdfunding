# Sequence Crowdfunding (MOTHER → Websites)

Modular monolith: Flask REST API (`backend/`) + Next.js frontend (`frontend/`) + PostgreSQL.

## Run locally
```bash
# backend (Python 3.13)
cd backend && python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # point DATABASE_URL / TEST_DATABASE_URL at your Postgres
export FLASK_APP="app:create_app"
flask db upgrade
flask create-staff you@example.com "Your Name" --role admin
python -m pytest                # needs a crowdfund_test database
gunicorn -b 127.0.0.1:5000 "app:create_app()"

# frontend (Node 22)
cd frontend && npm install && npm run build && npm start   # proxies /api/* to API_URL (default :5000)
```

## Trying payments in test mode
```bash
export CONTRIBUTIONS_MODE=simulated PAYMENT_WEBHOOK_SECRET=dev-secret   # then restart the API
flask mock-pay <provider_ref>      # delivers a signed webhook; use --event payment.failed etc.
```
Simulated payments are labelled as test payments and are never counted as money raised or revenue.
Verification and reset emails land in the `email_outbox` table until a mail provider is configured.

## Staff accounts
`flask create-staff` prompts for a password. Staff use `/staff` (review desk) after logging in.

## What is deliberately NOT built or enabled
- No real payment provider. Only a mock exists, so `confirmed_raised_cents` stays 0 until a live provider is approved and added.
- The investment funding model is registered but cannot be selected.
- The R500 pitch-deck fee is configuration (`PITCH_DECK_FEE_ZAR_CENTS`, `PITCH_DECK_FEE_SERVICE`, provisional value "package"). Charging is off until `PITCH_DECK_FEE_CHARGING_ENABLED=true` and a payment mode is active.
- The AI provider is a rule-based completeness checker, not a language model (see `docs/DECISIONS.md`).

See `docs/DECISIONS.md` and `docs/OPEN_QUESTIONS.md`.
