# Claim AI — Backend Local Development Setup

This README covers how to run the FastAPI backend locally, and how to troubleshoot the most common
issue: the app hanging on startup because it can't reach the Azure PostgreSQL database.

## Prerequisites

- Python 3.12
- A virtual environment set up in `backend/.venv`
- Access to the shared `.env` file (contact a teammate — **never commit this file**)
- Your current public IP added to the Azure PostgreSQL server's firewall rules (see below)

## Running the backend

```bash
cd backend
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Once running:

- http://127.0.0.1:8000/ui — temporary HTML test UI (claimant + assessor)
- http://127.0.0.1:8000/docs — OpenAPI for the JSON API Vue will use (`/api/...`)
- http://127.0.0.1:8000/health — liveness check

The HTML under `/ui` is throwaway. New product behaviour belongs in `app/api` and `app/services`.

## Environment variables

The app reads its database connection string from a `.env` file in `backend/`:
