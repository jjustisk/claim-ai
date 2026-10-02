# Claim AI — Frontend (Phase 3 scaffold)

Vue 3 + Vite + Tailwind. Built against the exact `claim-ai` backend API
contract (checked directly against `claims.py` / `auth.py` / `assessor_service.py`
/ `claim_service.py` as of commit 5d8b2f4).

## Setup
```bash
npm install
cp .env.example .env   # optional — defaults to the Vite dev proxy below
npm run dev
```
Assumes the backend is running on `http://127.0.0.1:8000` (see the proxy
in `vite.config.js`). Set `VITE_API_BASE_URL` in `.env` if yours runs
elsewhere.

## What's built (maps to Phase 3 steps 1 and 2, partially 4)
- Login (`/login`) — real JWT auth against `POST /api/auth/login`.
- Role-based routing guard — assessors and claimants land on different
  home routes and can't cross into each other's pages even if they
  guess a URL (the backend still enforces this too, this is just UX).
- Assessor queue (`/assessor`) — lists claims via `GET /api/claims`,
  sorted by priority_level + fraud_risk_score (see note below).
- Assessor claim detail (`/assessor/claims/:id`) — AI recommendation
  panel, evidence links, review history, and approve/reject/escalate
  actions wired to `POST /api/claims/{id}/review`. Surfaces the fraud
  image-similarity flag when present.
- Customer claim list (`/my-claims`) and status view (`/my-claims/:id`)
  — basic 3-step status tracker from `GET /api/claims/mine/{id}`.

## Known gaps — real backend work needed, not just frontend
These aren't bugs in this scaffold, they're missing data on the
backend that the Phase 3 step list calls for:

1. **No confidence band on the list endpoint.** `GET /api/claims`
   doesn't return the AI confidence band — only `priority_level` and
   `fraud_risk_score`. The queue currently sorts by those as the best
   available proxy. If "prioritised by AI confidence" is a real
   requirement, `list_claims()` in `assessor_service.py` needs to join
   `ai_decision` and the band computation needs to be exposed.
2. **No milestone/stage timestamps for customers.** `get_customer_claim()`
   only returns `submission_date` and `outcome_date` — there's no
   "AI review started" / "sent to assessor" timestamp anywhere, and no
   `customer_explanation` from `ai_decision` is joined in either. The
   status view approximates a 3-step timeline from what exists now;
   a real milestone timeline needs either a status-history table or
   at minimum joining `ai_decision.customer_explanation` in.
3. **No dedicated audit trail endpoint.** The audit log data exists
   (`audit_log` table) but there's no `/claims/{id}/audit` route —
   only a narrow slice of it (fraud image-similarity) gets pulled into
   `get_claim()`. Step 3 of Phase 3 (audit trail view) needs this
   built before the frontend can show it.
