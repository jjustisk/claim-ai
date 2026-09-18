"""HTML page for manually testing orchestration end to end.

Enter a claim_id (must already have real images attached via ClaimDocument),
runs Call 1 -> Call 2 + CRAG retrieval + Generation in one go and shows the
resulting decision plus the full per-stage audit trail (what each of Call 1
/ Call 2 / Generation logged against the shared ai_decision row).

Reset clears a claim's prior AIDecision/AuditLog/ClaimDamageAssessment rows
so the same claim can be re-run cleanly - each pipeline run creates a fresh
ai_decision row once the shared "pending" one is finalized, so repeated
manual testing on one claim otherwise just accumulates history.

Mounted on the main app at /ui/orchestration-test. Temporary test UI, same
pattern as /ui/pds-search.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.models import AIDecision, AuditLog, ClaimDamageAssessment
from app.connectors.db import get_db
from app.pages.ui_session import require_ui_role
from app.services.ai_pipeline_service import run_decision_pipeline

router = APIRouter(prefix="/ui/orchestration-test", include_in_schema=False)


async def _audit_trail_for_claim(db: AsyncSession, claim_id: int) -> list[dict]:
    """Most recent ai_decision row for this claim, plus its audit_log entries."""
    decision = (
        await db.execute(
            select(AIDecision)
            .where(AIDecision.claim_id == claim_id)
            .order_by(AIDecision.created_at.desc())
            .limit(1)
        )
    ).scalars().first()
    if decision is None:
        return []

    logs = (
        await db.execute(
            select(AuditLog).where(AuditLog.decision_id == decision.decision_id).order_by(AuditLog.timestamp)
        )
    ).scalars().all()
    return [
        {
            "stage": log.action_type,
            "description": log.description,
            "input_payload": log.input_payload,
            "output_payload": log.output_payload,
            "model_name": log.model_name,
            "timestamp": log.timestamp.isoformat() if log.timestamp else None,
        }
        for log in logs
    ]


INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Orchestration Test</title>
  <style>
    * { box-sizing: border-box; }
    body {
      font-family: system-ui, -apple-system, sans-serif;
      max-width: 780px;
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
    .btn-row { display: flex; gap: 0.6rem; margin-top: 1.1rem; }
    button.run-btn {
      background: #2563eb;
      color: #fff;
      border: none;
      border-radius: 8px;
      padding: 0.6rem 1.4rem;
      font-size: 0.95rem;
      cursor: pointer;
    }
    button.reset-btn {
      background: #fff;
      color: #991b1b;
      border: 1px solid #fca5a5;
      border-radius: 8px;
      padding: 0.6rem 1.1rem;
      font-size: 0.9rem;
      cursor: pointer;
    }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    #status {
      margin-top: 1rem;
      padding: 0.75rem 1rem;
      border-radius: 8px;
      display: none;
    }
    #status.err { display: block; background: #fee2e2; color: #991b1b; }
    #status.info { display: block; background: #eff6ff; color: #1e40af; }
    #status.ok { display: block; background: #dcfce7; color: #166534; }
    section { margin-top: 1.5rem; }
    h3.section-heading { font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.03em; color: #64748b; margin: 1.4rem 0 0.6rem; }
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
    .stage-card {
      background: #fff;
      border-radius: 10px;
      padding: 0.9rem 1.1rem;
      margin-bottom: 0.7rem;
      border-left: 4px solid #7c3aed;
    }
    .stage-card h2 {
      font-size: 0.78rem; font-weight: 700; text-transform: uppercase;
      letter-spacing: 0.03em; color: #5b21b6; margin: 0 0 0.35rem;
    }
    .stage-card .stage-desc { font-size: 0.88rem; margin: 0 0 0.5rem; }
    .stage-card details { font-size: 0.8rem; }
    .stage-card summary { cursor: pointer; color: #64748b; }
    .stage-card pre {
      white-space: pre-wrap; font-family: monospace; font-size: 0.78rem;
      background: #f8f9fb; padding: 0.5rem; border-radius: 6px; margin: 0.4rem 0 0;
    }
    .stage-card .model-name { color: #94a3b8; font-size: 0.75rem; float: right; }
    #empty { color: #64748b; font-size: 0.9rem; }
  </style>
</head>
<body>
  <h1>Orchestration Test</h1>
  <p class="meta">Runs the full pipeline for an existing claim — Call 1 (VLM damage assessment), then Generation (Call 2 + CRAG retrieval + composite-scored decision) — and shows the resulting decision plus the per-stage audit trail.</p>

  <label for="claim_id">Claim ID</label>
  <input type="number" id="claim_id" value="__DEFAULT_CLAIM_ID__" min="1" />

  <div class="btn-row">
    <button class="run-btn" id="run-btn" type="button">Run Pipeline</button>
    <button class="reset-btn" id="reset-btn" type="button">Reset audit trail for this claim</button>
  </div>

  <div id="status"></div>

  <section>
    <div id="results"><p id="empty">No run yet.</p></div>
    <div id="audit-trail"></div>
  </section>

  <script>
    const claimIdInput = document.getElementById("claim_id");
    const runBtn = document.getElementById("run-btn");
    const resetBtn = document.getElementById("reset-btn");
    const statusEl = document.getElementById("status");
    const resultsEl = document.getElementById("results");
    const auditEl = document.getElementById("audit-trail");

    function setStatus(message, cls) {
      statusEl.className = cls;
      statusEl.textContent = message;
    }

    function clearStatus() {
      statusEl.className = "";
      statusEl.textContent = "";
    }

    function escapeHtml(str) {
      const div = document.createElement("div");
      div.textContent = str;
      return div.innerHTML;
    }

    function renderAuditTrail(stages) {
      if (!stages || !stages.length) {
        auditEl.innerHTML = "";
        return;
      }
      const cards = stages.map((s) => `
        <div class="stage-card">
          <h2>${escapeHtml(s.stage)} <span class="model-name">${escapeHtml(s.model_name || "")}</span></h2>
          <p class="stage-desc">${escapeHtml(s.description || "")}</p>
          <details>
            <summary>input / output payload</summary>
            <pre>input:  ${escapeHtml(JSON.stringify(s.input_payload, null, 2))}</pre>
            <pre>output: ${escapeHtml(JSON.stringify(s.output_payload, null, 2))}</pre>
          </details>
        </div>
      `).join("");
      auditEl.innerHTML = `<h3 class="section-heading">Audit trail</h3>${cards}`;
    }

    async function runPipeline() {
      const claimId = claimIdInput.value.trim();
      if (!claimId) {
        setStatus("Enter a claim ID first.", "err");
        return;
      }
      clearStatus();
      runBtn.disabled = true;
      resultsEl.innerHTML = "<p id=\\"empty\\">Running… (Call 1, then Call 2 + retrieval + Generation)</p>";
      auditEl.innerHTML = "";

      try {
        const res = await fetch(`/ui/orchestration-test/api/run?claim_id=${encodeURIComponent(claimId)}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Pipeline run failed");

        renderAuditTrail(data.audit_trail);

        if (data.referred_no_images) {
          setStatus("Call 1 could not assess the images — claim referred to assessor before Generation ran.", "info");
          resultsEl.innerHTML = "";
          return;
        }

        const payoutLine = data.suggested_payout !== null
          ? `<h2>Suggested payout</h2><pre>$${data.suggested_payout.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</pre>`
          : "";
        resultsEl.innerHTML = `
          <div class="card ${data.decision}">
            <span class="badge">${escapeHtml(data.decision)}</span>
            <span class="conf">${data.confidence_score !== null ? "confidence " + data.confidence_score.toFixed(1) : "no score (referred before scoring)"}</span>
            <h2>Reason summary</h2>
            <pre>${escapeHtml(data.reason_summary || "")}</pre>
            ${payoutLine}
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
        setStatus(err.message, "err");
        resultsEl.innerHTML = "";
      } finally {
        runBtn.disabled = false;
      }
    }

    async function resetTrail() {
      const claimId = claimIdInput.value.trim();
      if (!claimId) {
        setStatus("Enter a claim ID first.", "err");
        return;
      }
      resetBtn.disabled = true;
      try {
        const res = await fetch(`/ui/orchestration-test/api/reset?claim_id=${encodeURIComponent(claimId)}`, { method: "POST" });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Reset failed");
        setStatus(`Cleared ${data.deleted_decisions} decision(s), ${data.deleted_audit_logs} audit log entr${data.deleted_audit_logs === 1 ? "y" : "ies"}, ${data.deleted_assessments} assessment(s) for claim_id=${claimId}.`, "ok");
        resultsEl.innerHTML = "<p id=\\"empty\\">No run yet.</p>";
        auditEl.innerHTML = "";
      } catch (err) {
        setStatus(err.message, "err");
      } finally {
        resetBtn.disabled = false;
      }
    }

    runBtn.addEventListener("click", runPipeline);
    resetBtn.addEventListener("click", resetTrail);
    claimIdInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") runPipeline();
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
    raw_claim_id = request.query_params.get("claim_id", "14")
    default_claim_id = raw_claim_id if raw_claim_id.isdigit() else "14"
    html = INDEX_HTML.replace("__DEFAULT_CLAIM_ID__", default_claim_id)
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@router.get("/api/run")
async def run(request: Request, claim_id: int, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    auth = require_ui_role(request, "assessor")
    if isinstance(auth, RedirectResponse):
        raise HTTPException(401, "Assessor sign-in required.")
    try:
        record = await run_decision_pipeline(claim_id, db)
    except Exception as exc:
        raise HTTPException(500, f"Pipeline run failed: {exc}") from exc

    audit_trail = await _audit_trail_for_claim(db, claim_id)

    if record is None:
        return JSONResponse({"referred_no_images": True, "audit_trail": audit_trail})

    return JSONResponse(
        {
            "referred_no_images": False,
            "decision": record.decision,
            "confidence_score": record.confidence_score,
            "suggested_payout": float(record.suggested_payout) if record.suggested_payout is not None else None,
            "reason_summary": record.reason_summary,
            "customer_explanation": record.customer_explanation,
            "assessor_memo": record.assessor_memo,
            "audit_trail": audit_trail,
        }
    )


@router.post("/api/reset")
async def reset(request: Request, claim_id: int, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Deletes this claim's AIDecision/AuditLog/ClaimDamageAssessment rows so
    it can be re-run cleanly. Does not touch the claim, its policy/customer,
    or its uploaded images - only prior pipeline-run history.
    """
    auth = require_ui_role(request, "assessor")
    if isinstance(auth, RedirectResponse):
        raise HTTPException(401, "Assessor sign-in required.")

    decision_ids = (
        await db.execute(select(AIDecision.decision_id).where(AIDecision.claim_id == claim_id))
    ).scalars().all()

    deleted_audit_logs = 0
    if decision_ids:
        result = await db.execute(delete(AuditLog).where(AuditLog.decision_id.in_(decision_ids)))
        deleted_audit_logs = result.rowcount or 0

    result = await db.execute(delete(AIDecision).where(AIDecision.claim_id == claim_id))
    deleted_decisions = result.rowcount or 0

    result = await db.execute(delete(ClaimDamageAssessment).where(ClaimDamageAssessment.claim_id == claim_id))
    deleted_assessments = result.rowcount or 0

    await db.commit()

    return JSONResponse(
        {
            "deleted_decisions": deleted_decisions,
            "deleted_audit_logs": deleted_audit_logs,
            "deleted_assessments": deleted_assessments,
        }
    )
