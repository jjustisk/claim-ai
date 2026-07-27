# Claim AI

AI-assisted insurance claims platform. See `docs/` for the Semester 1 design documentation
and the Semester 2 implementation plan.

## Repo layout

```
backend/    FastAPI app
frontend/   Vue 3 + Tailwind app
infra/      Azure resource definitions, local docker-compose
docs/       Design doc, semester plan, ADRs
```

## Setup

1. Copy `.env.example` to `.env` and fill in values (ask Justis/Hassan for shared dev credentials).
2. Backend: see `backend/README.md`
3. Frontend: see `frontend/README.md` (added once the frontend scaffold lands)

## Branching & PRs

- `main` is protected: PRs only, 1 approval required, CI must pass.
- Branch naming: `feat/short-description`, `fix/short-description`.
