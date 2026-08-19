"""Temporary HTML test UI for claimants and assessors.

Delete this module when Vue is ready. Vue should call `/api/...`, not these
routes. Until then, pages call the same services the JSON API uses.
"""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.db import get_db
from app.services.assessor_service import (
    REVIEW_OUTCOMES,
    STATUS_LABELS,
    ReviewError,
    claim_counts,
    download_claim_document,
    get_claim,
    list_claims,
    save_review,
)
from app.services.auth_service import (
    InvalidCredentials,
    authenticate,
    session_from_token,
)
from app.services.claim_service import ClaimSubmitError, list_policies, submit_claim

COOKIE_TOKEN = "claim_ai_token"
COOKIE_EMAIL = "claim_ai_email"

router = APIRouter(prefix="/ui", include_in_schema=False)


def home_path_for_role(role: str) -> str:
    return "/ui/dashboard" if role == "assessor" else "/ui/claim"


def _fmt_dt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    return str(value)


def _fmt_money(value: Any) -> str:
    if value is None:
        return "—"
    return f"{value:,.2f}"


def _styles() -> str:
    return """
:root {
  --brand: #0078d4; --brand-hover: #106ebe; --brand-press: #005a9e;
  --bg: #f5f5f5; --surface: #ffffff; --text: #242424; --muted: #616161;
  --stroke: #d1d1d1; --stroke-strong: #8a8886;
  --danger: #c50f1f; --danger-bg: #fde7e9; --success: #0e700e; --success-bg: #dff6dd;
  --info-bg: #ebf3fc; --warn: #8a6116; --warn-bg: #fff4ce; --nav: #201f1e;
  --header-h: 48px; --rail-w: 228px; --focus: 0 0 0 2px #fff, 0 0 0 4px var(--brand);
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  font-family: "Segoe UI", "Segoe UI Web (West European)", -apple-system, BlinkMacSystemFont, Roboto, "Helvetica Neue", sans-serif;
  color: var(--text); background: var(--bg); min-height: 100vh;
}
a { color: var(--brand); text-decoration: none; }
a:hover { text-decoration: underline; }
.brand-mark {
  width: 22px; height: 22px; border-radius: 4px; background: var(--brand); color: #fff;
  display: grid; place-items: center; font-size: 13px; font-weight: 700; line-height: 1;
}
.login-shell {
  min-height: 100vh; display: flex; flex-direction: column; align-items: center;
  justify-content: center; padding: 32px 16px; background: #f2f2f2;
}
.login-card {
  width: 100%; max-width: 440px; background: var(--surface);
  padding: 44px 44px 36px; box-shadow: 0 2px 6px rgba(0,0,0,.12);
}
.login-brand { display: flex; align-items: center; gap: 10px; margin-bottom: 24px; font-size: 15px; font-weight: 600; }
.login-card h1 { font-size: 24px; font-weight: 600; margin: 0 0 8px; }
.login-card .lede { color: var(--muted); font-size: 15px; margin: 0 0 24px; line-height: 20px; }
.field { margin-bottom: 20px; }
.field label { display: block; font-size: 14px; font-weight: 600; margin-bottom: 6px; }
.field input, .field select, .field textarea {
  width: 100%; height: 32px; border: 1px solid var(--stroke-strong); border-radius: 2px;
  padding: 0 8px; font: inherit; font-size: 14px; background: var(--surface); color: var(--text);
}
.field textarea { height: 120px; padding: 8px; resize: vertical; line-height: 20px; }
.field input:focus, .field select:focus, .field textarea:focus {
  outline: none; border-color: var(--brand); box-shadow: 0 0 0 1px var(--brand);
}
.hint { font-size: 12px; color: var(--muted); margin-top: 6px; }
.btn {
  display: inline-flex; align-items: center; justify-content: center; min-width: 108px;
  height: 32px; padding: 0 20px; border: 1px solid transparent; border-radius: 2px;
  font: inherit; font-size: 14px; font-weight: 600; cursor: pointer;
}
.btn-primary { background: var(--brand); color: #fff; }
.btn-primary:hover { background: var(--brand-hover); }
.btn-secondary { background: var(--surface); color: var(--text); border-color: var(--stroke-strong); }
.btn-secondary:hover { background: #f3f2f1; }
.login-actions { display: flex; justify-content: flex-end; margin-top: 8px; }
.banner { display: flex; gap: 12px; padding: 11px 12px; margin-bottom: 20px; border-radius: 4px; font-size: 14px; line-height: 20px; }
.banner:before { content: ""; width: 4px; border-radius: 2px; flex-shrink: 0; }
.banner-error { background: var(--danger-bg); }
.banner-error:before { background: var(--danger); }
.banner-success { background: var(--success-bg); }
.banner-success:before { background: var(--success); }
.banner-info { background: var(--info-bg); }
.banner-info:before { background: var(--brand); }
.login-foot { margin-top: 28px; font-size: 12px; color: var(--muted); }
.topbar {
  position: sticky; top: 0; z-index: 10; height: var(--header-h);
  background: var(--surface); border-bottom: 1px solid var(--stroke);
  display: flex; align-items: center; padding: 0 16px; gap: 12px;
}
.topbar .product { display: flex; align-items: center; gap: 10px; font-weight: 600; font-size: 16px; }
.topbar .spacer { flex: 1; }
.user-chip { display: flex; align-items: center; gap: 10px; font-size: 13px; }
.avatar {
  width: 28px; height: 28px; border-radius: 50%; background: #5c2e91; color: #fff;
  display: grid; place-items: center; font-size: 12px; font-weight: 600;
}
.layout { display: flex; min-height: calc(100vh - var(--header-h)); }
.rail { width: var(--rail-w); background: var(--nav); color: #fff; padding: 8px 0; flex-shrink: 0; }
.rail a { display: flex; color: #fff; text-decoration: none; padding: 8px 16px; font-size: 14px; border-left: 3px solid transparent; }
.rail a:hover { background: #323130; text-decoration: none; }
.rail a.active { background: #3b3a39; border-left-color: var(--brand); }
.main { flex: 1; padding: 20px 28px 48px; max-width: 1180px; }
.crumbs { font-size: 12px; color: var(--muted); margin-bottom: 8px; }
.page-title { margin: 0 0 4px; font-size: 28px; font-weight: 600; }
.page-sub { margin: 0 0 20px; color: var(--muted); font-size: 14px; }
.card { background: var(--surface); border: 1px solid var(--stroke); border-radius: 4px; padding: 24px; margin-bottom: 16px; }
.card h2 { margin: 0 0 4px; font-size: 16px; font-weight: 600; }
.card .section-help { color: var(--muted); font-size: 13px; margin: 0 0 16px; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 16px; }
.kpi { background: var(--surface); border: 1px solid var(--stroke); border-radius: 4px; padding: 16px; }
.kpi .label { font-size: 12px; color: var(--muted); margin-bottom: 6px; }
.kpi .value { font-size: 24px; font-weight: 600; }
.filters { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }
.filter {
  display: inline-flex; align-items: center; height: 28px; padding: 0 12px;
  border: 1px solid var(--stroke-strong); border-radius: 16px; font-size: 12px; color: var(--text);
  background: var(--surface); text-decoration: none;
}
.filter:hover { background: #f3f2f1; text-decoration: none; }
.filter.active { background: var(--info-bg); border-color: var(--brand); color: var(--brand); font-weight: 600; }
table.data { width: 100%; border-collapse: collapse; font-size: 13px; }
table.data th { text-align: left; font-weight: 600; color: var(--muted); padding: 10px 12px; border-bottom: 1px solid var(--stroke); background: #fafafa; }
table.data td { padding: 10px 12px; border-bottom: 1px solid var(--stroke); }
table.data tbody tr:hover { background: #f3f2f1; }
.pill { display: inline-flex; align-items: center; height: 20px; padding: 0 8px; border-radius: 10px; font-size: 12px; font-weight: 600; white-space: nowrap; }
.pill-submitted { background: var(--info-bg); color: #004578; }
.pill-under_review { background: var(--warn-bg); color: var(--warn); }
.pill-approved { background: var(--success-bg); color: var(--success); }
.pill-rejected { background: var(--danger-bg); color: var(--danger); }
.pill-closed { background: #f3f2f1; color: var(--muted); }
.dl { display: grid; grid-template-columns: 180px 1fr; gap: 8px 16px; font-size: 14px; }
.dl dt { color: var(--muted); }
.dl dd { margin: 0; font-weight: 600; }
.result-grid { display: grid; grid-template-columns: 180px 1fr; gap: 8px 16px; font-size: 14px; }
.result-grid dt { color: var(--muted); }
.result-grid dd { margin: 0; font-weight: 600; }
.form-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 8px; padding-top: 16px; border-top: 1px solid var(--stroke); }
.file-drop input[type=file] { height: auto; padding: 8px; }
.empty { color: var(--muted); font-size: 14px; padding: 12px 0; }
@media (max-width: 800px) {
  .rail { display: none; }
  .login-card { padding: 28px 22px; }
  .main { padding: 16px; }
  .dl, .result-grid { grid-template-columns: 1fr; }
}
"""


def _brand_mark() -> str:
    return '<span class="brand-mark" aria-hidden="true">C</span>'


def _banner(kind: str, message: str) -> str:
    return f'<div class="banner banner-{html.escape(kind)}" role="alert">{html.escape(message)}</div>'


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>{_styles()}</style>
</head>
<body>
{body}
</body>
</html>"""
    )


def _portal_chrome(email: str, role: str, inner: str, active: str) -> str:
    initial = html.escape((email[:1] or "?").upper())
    safe_email = html.escape(email)
    if role == "assessor":
        nav = f'<a class="{"active" if active == "dashboard" else ""}" href="/ui/dashboard">Dashboard</a>'
    else:
        nav = f'<a class="{"active" if active == "claim" else ""}" href="/ui/claim">Submit a claim</a>'
    return f"""
<header class="topbar">
  <div class="product">{_brand_mark()} Claim AI</div>
  <div class="spacer"></div>
  <div class="user-chip">
    <div class="avatar" aria-hidden="true">{initial}</div>
    <span>{safe_email}</span>
    <a href="/ui/logout">Sign out</a>
  </div>
</header>
<div class="layout">
  <nav class="rail" aria-label="Claim AI">{nav}</nav>
  <main class="main">{inner}</main>
</div>
"""


def _status_pill(status: str) -> str:
    label = STATUS_LABELS.get(status, status.replace("_", " ").title())
    css = status if status in STATUS_LABELS else "closed"
    return f'<span class="pill pill-{html.escape(css)}">{html.escape(label)}</span>'


def _session(request: Request) -> dict | None:
    token = request.cookies.get(COOKIE_TOKEN)
    email = request.cookies.get(COOKIE_EMAIL)
    if not token or not email:
        return None
    session = session_from_token(token)
    if session is None:
        return None
    session["token"] = token
    session["email"] = email
    return session


def _require_role(request: Request, role: str) -> dict | RedirectResponse:
    session = _session(request)
    if not session:
        return RedirectResponse("/ui/login", status_code=303)
    if session["role"] != role:
        return RedirectResponse(home_path_for_role(session["role"]), status_code=303)
    return session


def _login_view(error: str | None = None) -> HTMLResponse:
    banners = _banner("error", error) if error else ""
    body = f"""
<div class="login-shell">
  <form class="login-card" method="post" action="/ui/login" autocomplete="on">
    <div class="login-brand">{_brand_mark()} Claim AI</div>
    <h1>Sign in</h1>
    <p class="lede">Use your Claim AI account. Claimants can submit claims. Assessors can review them.</p>
    {banners}
    <div class="field">
      <label for="email">Email</label>
      <input id="email" name="email" type="email" required autofocus placeholder="name@example.com">
    </div>
    <div class="field">
      <label for="password">Password</label>
      <input id="password" name="password" type="password" required>
    </div>
    <div class="login-actions">
      <button class="btn btn-primary" type="submit">Sign in</button>
    </div>
    <p class="login-foot">One portal for claimants and assessors.</p>
  </form>
</div>
"""
    return _page("Sign in | Claim AI", body)


def _dashboard_view(email: str, role: str, *, status: str | None = None, error: str | None = None) -> HTMLResponse:
    banners = _banner("error", error) if error else ""
    try:
        counts = claim_counts()
        claims = list_claims(status)
        load_error = None
    except Exception as exc:
        counts = {"all": 0}
        claims = []
        load_error = f"Could not load claims: {exc}"
    if load_error:
        banners += _banner("error", load_error)

    kpi_items = [
        ("All claims", counts.get("all", 0)),
        ("Submitted", counts.get("submitted", 0)),
        ("Under review", counts.get("under_review", 0)),
        ("Approved", counts.get("approved", 0)),
        ("Rejected", counts.get("rejected", 0)),
    ]
    kpis = "".join(
        f'<div class="kpi"><div class="label">{html.escape(label)}</div>'
        f'<div class="value">{value}</div></div>'
        for label, value in kpi_items
    )
    filters = [("All", None)] + [(STATUS_LABELS[key], key) for key in STATUS_LABELS]
    filter_html = []
    for label, key in filters:
        href = "/ui/dashboard" if key is None else f"/ui/dashboard?status={quote(key)}"
        active = "active" if key == status else ""
        filter_html.append(f'<a class="filter {active}" href="{href}">{html.escape(label)}</a>')

    if claims:
        rows = []
        for claim in claims:
            claim_id = int(claim["claim_id"])
            rows.append(
                f"""<tr>
                  <td><a href="/ui/claims/{claim_id}">{html.escape(str(claim["claim_reference"]))}</a></td>
                  <td>{html.escape(str(claim["customer_name"]))}<div class="hint">{html.escape(str(claim["customer_email"]))}</div></td>
                  <td>{html.escape(str(claim["policy_number"]))}</td>
                  <td>{_status_pill(str(claim["status"]))}</td>
                  <td>{html.escape(_fmt_dt(claim["submission_date"]))}</td>
                  <td>{html.escape(str(claim["priority_level"] if claim["priority_level"] is not None else 0))}</td>
                  <td>{html.escape(str(claim["fraud_risk_score"] if claim["fraud_risk_score"] is not None else 0))}</td>
                </tr>"""
            )
        table = f"""
        <table class="data">
          <thead>
            <tr>
              <th>Reference</th><th>Customer</th><th>Policy</th>
              <th>Status</th><th>Submitted</th><th>Priority</th><th>Fraud score</th>
            </tr>
          </thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
        """
    else:
        table = '<p class="empty">No claims match this filter.</p>'

    inner = f"""
    <div class="crumbs">Claim AI &gt; Dashboard</div>
    <h1 class="page-title">Assessor dashboard</h1>
    <p class="page-sub">Review submitted claims, inspect evidence, and record an outcome.</p>
    {banners}
    <div class="kpis">{kpis}</div>
    <div class="card">
      <h2>Claims queue</h2>
      <p class="section-help">Open a claim reference to view documents and submit a review.</p>
      <div class="filters">{''.join(filter_html)}</div>
      {table}
    </div>
    """
    return _page("Dashboard | Claim AI", _portal_chrome(email, role, inner, "dashboard"))


def _claim_detail_view(
    email: str,
    role: str,
    claim: dict[str, Any],
    *,
    error: str | None = None,
    success: str | None = None,
) -> HTMLResponse:
    banners = ""
    if error:
        banners += _banner("error", error)
    if success:
        banners += _banner("success", success)

    coverage = claim.get("coverage_type") or "—"
    documents = claim.get("documents") or []
    if documents:
        doc_rows = []
        for doc in documents:
            name = Path(str(doc["file_url"] or "")).name or f"document-{doc['doc_id']}"
            doc_rows.append(
                f"""<tr>
                  <td>{html.escape(name)}</td>
                  <td>{html.escape(str(doc["file_type"] or "—"))}</td>
                  <td>{html.escape(_fmt_dt(doc["upload_date"]))}</td>
                  <td><a href="/ui/documents/{int(doc["doc_id"])}">Download</a></td>
                </tr>"""
            )
        docs_html = f"""
        <table class="data">
          <thead><tr><th>File</th><th>Type</th><th>Uploaded</th><th></th></tr></thead>
          <tbody>{''.join(doc_rows)}</tbody>
        </table>
        """
    else:
        docs_html = '<p class="empty">No supporting files were uploaded with this claim.</p>'

    decisions = claim.get("ai_decisions") or []
    if decisions:
        decision_rows = []
        for decision in decisions:
            decision_rows.append(
                f"""<tr>
                  <td>{html.escape(str(decision["decision"] or "—"))}</td>
                  <td>{html.escape(str(decision["confidence_score"] if decision["confidence_score"] is not None else "—"))}</td>
                  <td>{html.escape(str(decision["reason_summary"] or "—"))}</td>
                  <td>{html.escape(_fmt_dt(decision["created_at"]))}</td>
                </tr>"""
            )
        ai_html = f"""
        <table class="data">
          <thead><tr><th>Decision</th><th>Confidence</th><th>Reason</th><th>Created</th></tr></thead>
          <tbody>{''.join(decision_rows)}</tbody>
        </table>
        """
    else:
        ai_html = '<p class="empty">No AI decision has been recorded yet.</p>'

    reviews = claim.get("reviews") or []
    if reviews:
        review_rows = []
        for review in reviews:
            review_rows.append(
                f"""<tr>
                  <td>{html.escape(str(review["name"] or review["email"]))}</td>
                  <td>{_status_pill(str(review["outcome"] or "submitted"))}</td>
                  <td>{"Yes" if review["decision_override"] else "No"}</td>
                  <td>{html.escape(str(review["override_reason"] or "—"))}</td>
                  <td>{html.escape(_fmt_dt(review["review_date"]))}</td>
                </tr>"""
            )
        reviews_html = f"""
        <table class="data">
          <thead><tr><th>Assessor</th><th>Outcome</th><th>Override</th><th>Notes</th><th>Date</th></tr></thead>
          <tbody>{''.join(review_rows)}</tbody>
        </table>
        """
    else:
        reviews_html = '<p class="empty">No assessor reviews yet.</p>'

    options = []
    current = str(claim["status"])
    for value in REVIEW_OUTCOMES:
        selected = "selected" if value == current else ""
        options.append(
            f'<option value="{html.escape(value)}" {selected}>{html.escape(STATUS_LABELS[value])}</option>'
        )

    claim_id = int(claim["claim_id"])
    inner = f"""
    <div class="crumbs"><a href="/ui/dashboard">Dashboard</a> &gt; {html.escape(str(claim["claim_reference"]))}</div>
    <h1 class="page-title">{html.escape(str(claim["claim_reference"]))}</h1>
    <p class="page-sub">Claim {claim_id} · {_status_pill(current)}</p>
    {banners}
    <div class="card">
      <h2>Claim details</h2>
      <dl class="dl">
        <dt>Customer</dt><dd>{html.escape(str(claim["customer_name"]))} ({html.escape(str(claim["customer_email"]))})</dd>
        <dt>Phone</dt><dd>{html.escape(str(claim["customer_phone"] or "—"))}</dd>
        <dt>Policy</dt><dd>{html.escape(str(claim["policy_number"]))} — {html.escape(str(coverage))}</dd>
        <dt>Submitted</dt><dd>{html.escape(_fmt_dt(claim["submission_date"]))}</dd>
        <dt>Outcome date</dt><dd>{html.escape(_fmt_dt(claim["outcome_date"]))}</dd>
        <dt>Priority</dt><dd>{html.escape(str(claim["priority_level"] if claim["priority_level"] is not None else 0))}</dd>
        <dt>Fraud score</dt><dd>{html.escape(str(claim["fraud_risk_score"] if claim["fraud_risk_score"] is not None else 0))}</dd>
        <dt>Cost</dt><dd>{html.escape(_fmt_money(claim["cost"]))}</dd>
      </dl>
    </div>
    <div class="card">
      <h2>Evidence</h2>
      <p class="section-help">Files uploaded with the claim.</p>
      {docs_html}
    </div>
    <div class="card">
      <h2>AI decisions</h2>
      {ai_html}
    </div>
    <div class="card">
      <h2>Reviews</h2>
      {reviews_html}
    </div>
    <form class="card" method="post" action="/ui/claims/{claim_id}/review">
      <h2>Record a review</h2>
      <p class="section-help">Saving a review updates the claim status. A reason is required when rejecting.</p>
      <div class="field">
        <label for="outcome">Outcome</label>
        <select id="outcome" name="outcome" required>{''.join(options)}</select>
      </div>
      <div class="field">
        <label for="notes">Notes</label>
        <textarea id="notes" name="notes" maxlength="4000" placeholder="Assessment notes or override reason"></textarea>
      </div>
      <div class="form-actions">
        <a class="btn btn-secondary" href="/ui/dashboard">Back to dashboard</a>
        <button class="btn btn-primary" type="submit">Save review</button>
      </div>
    </form>
    """
    return _page(f"{claim['claim_reference']} | Claim AI", _portal_chrome(email, role, inner, "dashboard"))


def _claim_submit_view(
    email: str,
    role: str,
    *,
    error: str | None = None,
    success: dict | None = None,
) -> HTMLResponse:
    banners = ""
    if error:
        banners += _banner("error", error)
    if success:
        banners += _banner("success", "Claim submitted. Evidence files were uploaded.")
        banners += f"""
        <div class="card" style="margin-bottom:20px">
          <h2>Submission details</h2>
          <p class="section-help">Keep this reference for follow-up.</p>
          <dl class="result-grid">
            <dt>Claim ID</dt><dd>{html.escape(str(success.get("claim_id", "")))}</dd>
            <dt>Claim reference</dt><dd>{html.escape(str(success.get("claim_reference", "")))}</dd>
            <dt>Status</dt><dd>{html.escape(str(success.get("status", "")))}</dd>
            <dt>Files uploaded</dt><dd>{html.escape(str(success.get("files_uploaded", "")))}</dd>
          </dl>
        </div>
        """

    try:
        policies = list_policies()
        policy_error = None
    except Exception as exc:
        policies = []
        policy_error = f"Could not load policies from PostgreSQL: {exc}"

    if policy_error:
        banners += _banner("error", policy_error)
    elif not policies:
        banners += _banner(
            "info",
            "No policies were found. Insert a row into the policy table, then refresh this page.",
        )

    options = ['<option value="">Select a policy</option>']
    for policy in policies:
        policy_id = policy["policy_id"]
        policy_number = str(policy["policy_number"])
        coverage_type = policy.get("coverage_type")
        label = html.escape(policy_number)
        if coverage_type:
            label = f"{label} — {html.escape(str(coverage_type))}"
        options.append(f'<option value="{policy_id}">{label}</option>')

    inner = f"""
    <div class="crumbs">Claim AI &gt; Submit a claim</div>
    <h1 class="page-title">Submit a claim</h1>
    <p class="page-sub">Provide the policy, a description of the incident, and supporting JPEG, PNG, or PDF files.</p>
    {banners}
    <form class="card" method="post" action="/ui/submit" enctype="multipart/form-data">
      <h2>Claim details</h2>
      <p class="section-help">All fields are required. Maximum file size is 25 MB per file.</p>
      <div class="field">
        <label for="policy_id">Policy</label>
        <select id="policy_id" name="policy_id" required>
          {''.join(options)}
        </select>
        <p class="hint">Choose the policy this claim should be filed against.</p>
      </div>
      <div class="field">
        <label for="description">Incident description</label>
        <textarea id="description" name="description" required maxlength="8000" placeholder="What happened, when, and where?"></textarea>
      </div>
      <div class="field file-drop">
        <label for="files">Supporting evidence</label>
        <input id="files" name="files" type="file" required multiple accept=".jpg,.jpeg,.png,.pdf,image/jpeg,image/png,application/pdf">
        <p class="hint">JPEG, PNG, or PDF. You can select more than one file.</p>
      </div>
      <div class="form-actions">
        <a class="btn btn-secondary" href="/ui/claim">Discard</a>
        <button class="btn btn-primary" type="submit">Submit claim</button>
      </div>
    </form>
    """
    return _page("Submit a claim | Claim AI", _portal_chrome(email, role, inner, "claim"))


@router.get("/", response_class=HTMLResponse)
def root(request: Request):
    session = _session(request)
    if session:
        return RedirectResponse(home_path_for_role(session["role"]), status_code=303)
    return RedirectResponse("/ui/login", status_code=303)


@router.get("/login", response_class=HTMLResponse)
def login_get(request: Request):
    session = _session(request)
    if session:
        return RedirectResponse(home_path_for_role(session["role"]), status_code=303)
    return _login_view()


@router.post("/login", response_class=HTMLResponse)
async def login_post(
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    email = email.strip()
    try:
        result = await authenticate(email, password, db)
    except InvalidCredentials:
        return _login_view("Incorrect email or password.")
    token = result["access_token"]
    session = session_from_token(token)
    if session is None:
        return _login_view("This account cannot use the Claim AI portal.")
    response = RedirectResponse(home_path_for_role(session["role"]), status_code=303)
    response.set_cookie(COOKIE_TOKEN, token, httponly=True, samesite="lax")
    response.set_cookie(COOKIE_EMAIL, email, httponly=True, samesite="lax")
    return response


@router.get("/logout")
def logout():
    response = RedirectResponse("/ui/login", status_code=303)
    response.delete_cookie(COOKIE_TOKEN)
    response.delete_cookie(COOKIE_EMAIL)
    return response


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, status: str | None = None):
    auth = _require_role(request, "assessor")
    if isinstance(auth, RedirectResponse):
        return auth
    if status and status not in STATUS_LABELS:
        status = None
    return _dashboard_view(auth["email"], auth["role"], status=status)


@router.get("/claims/{claim_id}", response_class=HTMLResponse)
def claim_detail(request: Request, claim_id: int):
    auth = _require_role(request, "assessor")
    if isinstance(auth, RedirectResponse):
        return auth
    try:
        claim = get_claim(claim_id)
    except Exception as exc:
        return _dashboard_view(auth["email"], auth["role"], error=f"Could not load claim: {exc}")
    if claim is None:
        return _dashboard_view(auth["email"], auth["role"], error="Claim not found.")
    return _claim_detail_view(auth["email"], auth["role"], claim)


@router.post("/claims/{claim_id}/review", response_class=HTMLResponse)
def claim_review(
    request: Request,
    claim_id: int,
    outcome: str = Form(...),
    notes: str = Form(""),
):
    auth = _require_role(request, "assessor")
    if isinstance(auth, RedirectResponse):
        return auth
    try:
        claim = get_claim(claim_id)
    except Exception as exc:
        return _dashboard_view(auth["email"], auth["role"], error=f"Could not load claim: {exc}")
    if claim is None:
        return _dashboard_view(auth["email"], auth["role"], error="Claim not found.")

    try:
        save_review(auth["id"], claim_id, outcome, notes)
        claim = get_claim(claim_id) or claim
    except ReviewError as exc:
        return _claim_detail_view(auth["email"], auth["role"], claim, error=str(exc))
    except Exception as exc:
        return _claim_detail_view(auth["email"], auth["role"], claim, error=f"Could not save review: {exc}")
    return _claim_detail_view(auth["email"], auth["role"], claim, success="Review saved.")


@router.get("/documents/{doc_id}")
async def download_document(request: Request, doc_id: int):
    auth = _require_role(request, "assessor")
    if isinstance(auth, RedirectResponse):
        return auth
    try:
        downloaded = await download_claim_document(doc_id)
    except Exception as exc:
        return _dashboard_view(auth["email"], auth["role"], error=f"Could not download file: {exc}")
    if downloaded is None:
        return _dashboard_view(auth["email"], auth["role"], error="Document not found.")
    data, filename, media_type = downloaded
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/claim", response_class=HTMLResponse)
def claim_get(request: Request):
    auth = _require_role(request, "claimant")
    if isinstance(auth, RedirectResponse):
        return auth
    return _claim_submit_view(auth["email"], auth["role"])


@router.post("/submit", response_class=HTMLResponse)
async def claim_submit(
    request: Request,
    policy_id: int = Form(...),
    description: str = Form(...),
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
):
    auth = _require_role(request, "claimant")
    if isinstance(auth, RedirectResponse):
        return auth

    description = description.strip()
    if not description:
        return _claim_submit_view(auth["email"], auth["role"], error="Description is required.")

    user = {"sub": str(auth["id"]), "role": auth["role"], "email": auth["email"]}
    try:
        result = await submit_claim(
            db=db,
            user=user,
            policy_id=policy_id,
            description=description,
            files=files,
        )
    except ClaimSubmitError as exc:
        return _claim_submit_view(auth["email"], auth["role"], error=str(exc))
    return _claim_submit_view(auth["email"], auth["role"], success=result)
