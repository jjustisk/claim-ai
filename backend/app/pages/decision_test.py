"""HTML page for manually testing Generation (Call A) end to end.

Enter a claim_id (must already have a Call 1 assessment), see the
composite-scored decision, confidence, reason summary, customer
explanation, and full assessor memo.

Mounted on the main app at /ui/decision-test. Temporary test UI, same
pattern as /ui/pds-search - delete once orchestration wires this into the
real claim flow.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.connectors.db import get_db
from app.pages.ui_session import require_ui_role
from app.services.damage_description_services import NoClaimImagesError
from app.services.decision_service import NoDamageAssessmentError, generate_decision

router = APIRouter(prefix="/ui/decision-test", include_in_schema=False)


INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Decision Generation Test</title>
  <style>
    * { box-sizing: border-box; }
    body {
      font-family: system-ui, -apple-system, sans-serif;
      max-width: 760px;
      margin: 2rem auto;
      padding: 0 1rem;
      color: #1a1a1a;
      background: #f8f9fb;
    }
    h1 { font-size: 1.5rem; margin-bottom: 0.25rem; }
    p.meta { color: #555; font-size: 0.9rem; margin-bottom: 1.5rem; }
    label { display: block; font-size: 0.875rem; font-weight: 600; margin: 0.9rem 0 0.3rem; }
    input[type="number"] {
      width: 100%;
      padding: 0.6rem 0.7rem;
      border: 1px solid #cbd5e1;
      border-radius: 8px;
      font-size: 0.95rem;
      background: #fff;
      font-family: inherit;
    }
    button.run-btn {
      margin-top: 1.1rem;
      background: #2563eb;
      color: #fff;
      border: none;
      border-radius: 8px;
      padding: 0.6rem 1.4rem;
      font-size: 0.95rem;
      cursor: pointer;
    }
    button.run-btn:disabled { opacity: 0.5; cursor: not-allowed; }
    #status {
      margin-top: 1rem;
      padding: 0.75rem 1rem;
      border-radius: 8px;
      display: none;
    }
    #status.err { display: block; background: #fee2e2; color: #991b1b; }
    section { margin-top: 1.5rem; }
    .card {
      background: #fff;
      border-radius: 10px;
      padding: 1rem 1.2rem;
      margin-bottom: 0.9rem;
      border-left: 4px solid #2563eb;
    }
    .card.covered { border-left-color: #16a34a; }
    .card.excluded { border-left-color: #dc2626; }
    .card.partial { border-left-color: #d97706; }
    .card.refer_to_assessor { border-left-color: #6b7280; }
    .card h2 {
      font-size: 0.8rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.03em;
      color: #555;
      margin: 0 0 0.5rem;
    }
    .card .badge {
      display: inline-block;
      font-weight: 700;
      text-transform: uppercase;
      font-size: 0.85rem;
      margin-bottom: 0.4rem;
    }
    .card .conf { float: right; color: #64748b; font-size: 0.85rem; font-weight: 400; }
    .card pre {
      white-space: pre-wrap;
      font-family: inherit;
      margin: 0.4rem 0 0;
      font-size: 0.9rem;
      line-height: 1.45;
    }
    #empty { color: #64748b; font-size: 0.9rem; }
  </style>
</head>
<body>
  <h1>Decision Generation Test</h1>
  <p class="meta">Manual test for Generation (Call A) — runs the composite-scored decision for an existing claim (must already have a Call 1 assessment).</p>

  <label for="claim_id">Claim ID</label>
  <input type="number" id="claim_id" value="14" min="1" />

  <button class="run-btn" id="run-btn" type="button">Generate Decision</button>

  <div id="status"></div>

  <section>
    <div id="results"><p id="empty">No run yet.</p></div>
  </section>

  <script>
    const claimIdInput = document.getElementById("claim_id");
    const runBtn = document.getElementById("run-btn");
    const statusEl = document.getElementById("status");
    const resultsEl = document.getElementById("results");

    function setError(message) {
      statusEl.className = "err";
      statusEl.textContent = message;
    }

    function clearError() {
      statusEl.className = "";
      statusEl.textContent = "";
    }

    function escapeHtml(str) {
      const div = document.createElement("div");
      div.textContent = str;
      return div.innerHTML;
    }

    async function runDecision() {
      const claimId = claimIdInput.value.trim();
      if (!claimId) {
        setError("Enter a claim ID first.");
        return;
      }
      clearError();
      runBtn.disabled = true;
      resultsEl.innerHTML = "<p id=\\"empty\\">Running…</p>";

      try {
        const res = await fetch(`/ui/decision-test/api/run?claim_id=${encodeURIComponent(claimId)}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Decision generation failed");

        resultsEl.innerHTML = `
          <div class="card ${data.decision}">
            <span class="badge">${escapeHtml(data.decision)}</span>
            <span class="conf">${data.confidence_score !== null ? "confidence " + data.confidence_score.toFixed(1) : "no score (referred before scoring)"}</span>
            <h2>Reason summary</h2>
            <pre>${escapeHtml(data.reason_summary || "")}</pre>
          </div>
          <div class="card">
            <h2>Customer explanation</h2>
            <pre>${escapeHtml(data.customer_explanation || "")}</pre>
          </div>
          <div class="card">
            <h2>Assessor memo</h2>
            <pre>${escapeHtml(data.assessor_memo || "")}</pre>
          </div>
        `;
      } catch (err) {
        setError(err.message);
        resultsEl.innerHTML = "";
      } finally {
        runBtn.disabled = false;
      }
    }

    runBtn.addEventListener("click", runDecision);
    claimIdInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") runDecision();
    });
  </script>
</body>
</html>
"""


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    auth = require_ui_role(request, "assessor")
    if isinstance(auth, RedirectResponse):
        return auth
    return INDEX_HTML


@router.get("/api/run")
async def run(request: Request, claim_id: int, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    auth = require_ui_role(request, "assessor")
    if isinstance(auth, RedirectResponse):
        raise HTTPException(401, "Assessor sign-in required.")
    try:
        record = await generate_decision(claim_id, db)
    except NoDamageAssessmentError as exc:
        raise HTTPException(400, str(exc)) from exc
    except NoClaimImagesError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Decision generation failed: {exc}") from exc
    return JSONResponse(
        {
            "decision": record.decision,
            "confidence_score": record.confidence_score,
            "reason_summary": record.reason_summary,
            "customer_explanation": record.customer_explanation,
            "assessor_memo": record.assessor_memo,
        }
    )
