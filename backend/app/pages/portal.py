"""Temporary HTML test UI for claimants and assessors.

Delete this module when Vue is ready. Vue should call `/api/...`, not these
routes. Until then, pages call the same services the JSON API uses.
"""

from __future__ import annotations

import html
from datetime import date, datetime
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.db import get_db
from app.pages.claim_form_html import render_claim_form_fields
from app.pages.ui_session import (
    COOKIE_EMAIL,
    COOKIE_TOKEN,
    home_path_for_role,
    require_ui_role,
    session_from_request,
)
from app.services.assessor_service import (
    REVIEW_OUTCOMES,
    STATUS_LABELS,
    ReviewError,
    claim_counts,
    download_claim_document,
    evidence_download_response,
    evidence_filename,
    get_claim,
    get_document,
    list_claims,
    save_review,
)
from app.services.auth_service import (
    InvalidCredentials,
    authenticate,
    session_from_token,
)
from app.services.claim_form import (
    claim_display_type,
    payload_from_form,
    posted_draft_from_payload,
)
from app.services.claim_service import (
    ClaimSubmitError,
    customer_owns_claim_document,
    delete_customer_draft,
    get_customer_claim,
    get_customer_profile,
    list_customer_claims,
    list_policies,
    submit_claim,
)

router = APIRouter(prefix="/ui", include_in_schema=False)


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


def _fmt_date(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    return str(value)


def _fmt_yes_no(value: Any) -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return "—"


def _date_input(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value)
    return text[:10]


def _attr(value: Any) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def _claim_type_label(value: Any, row: dict[str, Any] | None = None) -> str:
    if row:
        return claim_display_type(row)
    return claim_display_type({"insurance_type": value, "claim_type": value})


def _radio_row(name: str, current: Any, *, required: bool = False) -> str:
    req = "required" if required else ""
    yes = "checked" if current is True else ""
    no = "checked" if current is False else ""
    return f"""
      <div class="choice">
        <label><input type="radio" name="{name}" value="yes" {yes} {req}> Yes</label>
        <label><input type="radio" name="{name}" value="no" {no}> No</label>
      </div>
    """


def _styles() -> str:
    return """
:root {
  --brand: #0078d4; --brand-hover: #106ebe; --brand-press: #005a9e;
  --bg: #f5f5f5; --surface: #ffffff; --text: #242424; --muted: #616161;
  --stroke: #d1d1d1; --stroke-strong: #8a8886;
  --danger: #c50f1f; --danger-bg: #fde7e9; --success: #0e700e; --success-bg: #dff6dd;
  --info-bg: #ebf3fc; --warn: #8a6116; --warn-bg: #fff4ce; --nav: #fafafa;
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
  display: inline-flex; align-items: center; justify-content: center;
  min-width: max-content; min-height: 32px; height: 32px; padding: 0 16px;
  border: 1px solid transparent; border-radius: 2px;
  font: inherit; font-size: 14px; font-weight: 600; cursor: pointer;
  white-space: nowrap; line-height: 1; text-decoration: none; box-sizing: border-box;
}
.btn-primary { background: var(--brand); color: #fff; }
.btn-primary:hover { background: var(--brand-hover); }
.btn-danger { background: var(--surface); color: var(--danger); border-color: var(--danger); }
.btn-danger:hover { background: var(--danger-bg); }
.btn-link {
  min-width: 0; height: auto; padding: 0; background: none; border: 0;
  color: var(--danger); font: inherit; font-size: 13px; font-weight: 600; cursor: pointer;
}
.btn-link:hover { text-decoration: underline; }
.row-actions { display: flex; gap: 8px; align-items: center; flex-shrink: 0; flex-wrap: nowrap; }
.row-actions form { display: inline-flex; margin: 0; flex-shrink: 0; }
.progress {
  height: 6px; background: #edebe9; border-radius: 3px; overflow: hidden; width: 88px;
}
.progress > span { display: block; height: 100%; background: var(--brand); }
.resume {
  display: flex; justify-content: space-between; gap: 16px; align-items: center;
  background: var(--info-bg); border: 1px solid #c7e0f4; border-radius: 4px;
  padding: 20px 24px; margin-bottom: 16px;
}
.resume h2 { margin: 0 0 4px; font-size: 16px; }
.resume p { margin: 0; color: var(--muted); font-size: 13px; }
.tip { font-size: 13px; color: var(--muted); margin: 12px 0 0; }
.empty-hero { text-align: center; padding: 28px 16px; }
.empty-hero .mark {
  width: 48px; height: 48px; margin: 0 auto 12px; border-radius: 12px;
  background: var(--info-bg); color: var(--brand); display: grid; place-items: center;
  font-size: 22px; font-weight: 700;
}
.confetti { position: relative; overflow: hidden; }
.confetti:after {
  content: "✦  ✧  ★  ✦"; letter-spacing: 18px;
  position: absolute; right: 16px; top: 12px; color: var(--brand); opacity: .35;
  font-size: 14px; pointer-events: none;
}
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
.rail { width: var(--rail-w); background: var(--nav); color: var(--text); padding: 8px 0; flex-shrink: 0; border-right: 1px solid var(--stroke); }
.rail a { display: flex; color: var(--text); text-decoration: none; padding: 8px 16px; font-size: 14px; border-left: 3px solid transparent; }
.rail a:hover { background: #f3f2f1; text-decoration: none; }
.rail a.active { background: var(--info-bg); border-left-color: var(--brand); color: var(--brand); font-weight: 600; }
.main { flex: 1; padding: 20px 28px 48px; max-width: 1180px; }
.crumbs { font-size: 12px; color: var(--muted); margin-bottom: 8px; }
.page-title { margin: 0 0 4px; font-size: 28px; font-weight: 600; }
.page-sub { margin: 0 0 20px; color: var(--muted); font-size: 14px; }
.page-head { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 20px; }
.page-head > div:first-child { min-width: 0; }
.page-head .page-sub { margin-bottom: 0; }
.page-head .row-actions .btn { flex-shrink: 0; width: auto; }
.hero {
  background: var(--surface); border: 1px solid var(--stroke); border-radius: 4px;
  padding: 28px 24px; margin-bottom: 16px;
}
.hero h1 { margin: 0 0 8px; font-size: 28px; font-weight: 600; }
.hero p { margin: 0 0 16px; color: var(--muted); font-size: 15px; line-height: 22px; max-width: 42em; }
.topbar .btn { text-decoration: none; height: 28px; min-width: max-content; padding: 0 12px; font-size: 13px; white-space: nowrap; flex-shrink: 0; }
.topbar .btn:hover { text-decoration: none; }
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
.pill-draft { background: #f3f2f1; color: var(--muted); }
.dl { display: grid; grid-template-columns: 180px 1fr; gap: 8px 16px; font-size: 14px; }
.dl dt { color: var(--muted); }
.dl dd { margin: 0; font-weight: 600; }
.result-grid { display: grid; grid-template-columns: 180px 1fr; gap: 8px 16px; font-size: 14px; }
.result-grid dt { color: var(--muted); }
.result-grid dd { margin: 0; font-weight: 600; }
.form-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 8px; padding-top: 16px; border-top: 1px solid var(--stroke); }
.file-drop input[type=file] { height: auto; padding: 8px; }
.empty { color: var(--muted); font-size: 14px; padding: 12px 0; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 16px; }
.field-span { grid-column: 1 / -1; }
.choice { display: flex; gap: 18px; align-items: center; min-height: 32px; }
.choice label { display: inline-flex; align-items: center; gap: 6px; font-weight: 400; margin: 0; }
.choice input { width: auto; height: auto; margin: 0; }
.check-row { display: flex; align-items: flex-start; gap: 10px; }
.check-row input { width: auto; height: auto; margin-top: 3px; }
.check-row span { font-size: 14px; line-height: 20px; }
.req { color: var(--danger); }
.type-pick { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 0 0 24px; }
.type-card {
  display: flex; flex-direction: column; gap: 6px; border: 1px solid var(--stroke-strong);
  border-radius: 4px; padding: 16px; cursor: pointer; background: var(--surface);
}
.type-card-title { display: flex; flex-direction: row; align-items: center; gap: 8px; white-space: nowrap; }
.type-card-title input[type="radio"] {
  width: 16px; height: 16px; margin: 0; flex-shrink: 0; accent-color: var(--brand);
}
.type-card-title strong { font-size: 16px; line-height: 1.2; }
.type-card-help { color: var(--muted); font-size: 13px; line-height: 18px; font-weight: 400; padding-left: 24px; }
.type-card.selected, .type-card:has(input:checked) { border-color: var(--brand); background: var(--info-bg); }
.checkbox-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 8px 12px; }
.checkbox-grid label { display: flex; align-items: center; gap: 8px; font-weight: 400; margin: 0; }
.checkbox-grid input { width: auto; height: auto; margin: 0; }
.card h3 { margin: 16px 0 8px; font-size: 14px; font-weight: 600; }
.card h4 { margin: 12px 0 8px; font-size: 13px; font-weight: 600; color: var(--muted); }
@media (max-width: 800px) {
  .rail { display: none; }
  .login-card { padding: 28px 22px; }
  .main { padding: 16px; }
  .dl, .result-grid, .form-grid, .type-pick { grid-template-columns: 1fr; }
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


def _first_name(profile: dict[str, Any] | None, email: str) -> str:
    name = str((profile or {}).get("name") or "").strip()
    if name:
        return name.split()[0]
    local = email.split("@")[0].strip()
    return local[:1].upper() + local[1:] if local else "there"


def _day_greeting() -> str:
    hour = datetime.now().hour
    if hour < 12:
        return "Good morning"
    if hour < 17:
        return "Good afternoon"
    return "Good evening"


def _relative_time(value: Any) -> str:
    if not isinstance(value, datetime):
        return ""
    stamp = value.replace(tzinfo=None)
    minutes = int((datetime.utcnow() - stamp).total_seconds() // 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hr ago"
    days = hours // 24
    if days == 1:
        return "yesterday"
    return f"{days} days ago"


def _draft_progress(row: dict[str, Any]) -> int:
    checks = (
        row.get("insurance_type") or row.get("claim_type"),
        row.get("incident_date"),
        row.get("incident_location") or row.get("incident_street"),
        row.get("incident_description"),
        row.get("holder_first_name") or row.get("claimant_name"),
        row.get("claimant_phone") or row.get("holder_phone"),
        row.get("is_policyholder") is not None or row.get("others_involved") is not None,
    )
    filled = sum(1 for item in checks if item)
    return int(round(100 * filled / len(checks)))


_HOME_TIPS = (
    "You can submit even if you do not have every receipt yet.",
    "A couple of photos of the damage helps an assessor get started faster.",
    "Save a draft anytime. Nothing goes to an assessor until you submit.",
    "If someone else was involved, their registration number is especially useful.",
)


def _portal_chrome(email: str, role: str, inner: str, active: str) -> str:
    initial = html.escape((email[:1] or "?").upper())
    safe_email = html.escape(email)
    extra_actions = ""
    if role == "assessor":
        nav = f'<a class="{"active" if active == "dashboard" else ""}" href="/ui/dashboard">Dashboard</a>'
    else:
        nav = (
            f'<a class="{"active" if active == "home" else ""}" href="/ui/home">Home</a>'
            f'<a class="{"active" if active == "claim" else ""}" href="/ui/claim">Make a claim</a>'
        )
        extra_actions = '<a class="btn btn-primary" href="/ui/claim">Make a claim</a>'
    return f"""
<header class="topbar">
  <div class="product">{_brand_mark()} Claim AI</div>
  <div class="spacer"></div>
  {extra_actions}
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
    labels = {**STATUS_LABELS, "draft": "Draft"}
    label = labels.get(status, status.replace("_", " ").title())
    css = status if status in labels else "closed"
    return f'<span class="pill pill-{html.escape(css)}">{html.escape(label)}</span>'


def _session(request: Request) -> dict | None:
    return session_from_request(request)


def _require_role(request: Request, role: str) -> dict | RedirectResponse:
    return require_ui_role(request, role)


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


def _dl(rows: list[tuple[str, Any]]) -> str:
    items = []
    for label, value in rows:
        items.append(f"<dt>{html.escape(label)}</dt><dd>{html.escape(str(value if value not in (None, '') else '—'))}</dd>")
    return f'<dl class="dl">{"".join(items)}</dl>'


def _person_dl(title: str, prefix: str, data: dict[str, Any], extra: list[tuple[str, Any]] | None = None) -> str:
    name = " ".join(part for part in (data.get(f"{prefix}first_name") or data.get("first_name"), data.get(f"{prefix}last_name") or data.get("last_name")) if part)
    rows = [
        ("Title", data.get(f"{prefix}title") or data.get("title")),
        ("Name", name or None),
        ("Company", data.get(f"{prefix}company_name") or data.get("company_name")),
        ("Phone", data.get(f"{prefix}phone") or data.get("phone")),
        ("Email", data.get(f"{prefix}email") or data.get("email")),
        (
            "Address",
            ", ".join(
                str(part)
                for part in (
                    data.get(f"{prefix}unit") or data.get("unit"),
                    data.get(f"{prefix}street_number") or data.get("street_number"),
                    data.get(f"{prefix}street_name") or data.get("street_name"),
                    data.get(f"{prefix}suburb") or data.get("suburb"),
                    data.get(f"{prefix}state") or data.get("state"),
                    data.get(f"{prefix}postcode") or data.get("postcode"),
                )
                if part
            ) or None,
        ),
    ]
    if extra:
        rows.extend(extra)
    return f"<h3>{html.escape(title)}</h3>" + _dl(rows)


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
            name = evidence_filename(str(doc["file_url"] or ""), int(doc["doc_id"]))
            doc_rows.append(
                f"""<tr>
                  <td>{html.escape(name)}</td>
                  <td>{html.escape(str(doc["file_type"] or "—"))}</td>
                  <td>{html.escape(_fmt_dt(doc["upload_date"]))}</td>
                  <td><a href="/ui/documents/{int(doc["doc_id"])}" download="{html.escape(name, quote=True)}">Download</a></td>
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

    match = claim.get("similar_image_match")
    if match:
        level = "Strong match" if match["image_similarity_score"] == 1.0 else "Possible match"
        similar_match_html = f"""
        <div class="card">
          <h2>Possible image match</h2>
          <p class="section-help">
            {html.escape(level)} with a photo from another claim
            (Hamming distance {match["hamming_distance"]}). Please verify before relying on this.
          </p>
          <img src="/ui/documents/{int(match["matched_doc_id"])}" alt="Similar image from another claim"
               style="max-width:320px;border:1px solid #ddd;border-radius:4px;" />
          <p>
            <a href="/ui/claims/{int(match["matched_claim_id"])}">
              View claim {html.escape(str(match["matched_claim_reference"]))}
              ({html.escape(str(match["matched_customer_name"]))})
            </a>
          </p>
        </div>
        """
    else:
        similar_match_html = ""

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
    insurance = str(claim.get("insurance_type") or "")
    holder_name = " ".join(
        part for part in (claim.get("holder_first_name"), claim.get("holder_last_name")) if part
    ) or claim.get("claimant_name")
    holder_address = ", ".join(
        str(part)
        for part in (
            claim.get("holder_unit"),
            claim.get("holder_street_number"),
            claim.get("holder_street_name"),
            claim.get("holder_suburb"),
            claim.get("holder_state"),
            claim.get("holder_postcode"),
        )
        if part
    )
    incident_address = ", ".join(
        str(part)
        for part in (
            claim.get("incident_street"),
            claim.get("incident_cross_street"),
            claim.get("incident_suburb"),
            claim.get("incident_state"),
            claim.get("incident_postcode"),
        )
        if part
    ) or claim.get("incident_location")

    extra_cards = []
    if insurance == "motor":
        extra_cards.append(
            f"""
            <div class="card">
              <h2>Vehicle and driver</h2>
              {_dl([
                ("Registration", claim.get("vehicle_registration")),
                ("Type", claim.get("vehicle_type")),
                ("Year / make / model", " ".join(str(part) for part in (claim.get("vehicle_year"), claim.get("vehicle_make"), claim.get("vehicle_model")) if part) or None),
                ("Damage areas", claim.get("vehicle_damage_areas")),
                ("Towed", _fmt_yes_no(claim.get("vehicle_towed"))),
                ("Vehicle location", claim.get("vehicle_now_location")),
                ("Airbags deployed", _fmt_yes_no(claim.get("airbags_deployed"))),
                ("Over 40 km/h", _fmt_yes_no(claim.get("speed_over_40"))),
                ("Vehicle driven", _fmt_yes_no(claim.get("vehicle_driven"))),
                ("Policy holder was driver", _fmt_yes_no(claim.get("policyholder_was_driver"))),
                ("Driver", " ".join(part for part in (claim.get("driver_first_name"), claim.get("driver_last_name")) if part) or None),
                ("Licence number", claim.get("driver_licence_number")),
                ("Licence years held", claim.get("driver_licence_years")),
                ("Alcohol or drugs", _fmt_yes_no(claim.get("alcohol_or_drugs"))),
                ("Person injured", _fmt_yes_no(claim.get("person_injured"))),
              ])}
            </div>
            """
        )
    if insurance == "property":
        contents_rows = []
        for item in claim.get("contents_items") or []:
            contents_rows.append(
                f"<tr><td>{html.escape(str(item.get('category') or '—'))}</td>"
                f"<td>{html.escape(str(item.get('description') or '—'))}</td>"
                f"<td>{html.escape(_fmt_money(item.get('estimated_value')))}</td></tr>"
            )
        contents_html = (
            f'<table class="data"><thead><tr><th>Item</th><th>Description</th><th>Value</th></tr></thead>'
            f"<tbody>{''.join(contents_rows)}</tbody></table>"
            if contents_rows
            else '<p class="empty">No contents items listed.</p>'
        )
        extra_cards.append(
            f"""
            <div class="card">
              <h2>Building and contents</h2>
              {_dl([
                ("Building damaged", _fmt_yes_no(claim.get("building_damaged"))),
                ("Building areas", claim.get("building_areas")),
                ("Carpet", claim.get("damage_carpet")),
                ("Ceiling", claim.get("damage_ceiling")),
                ("Floor", claim.get("damage_floor")),
                ("Wall", claim.get("damage_wall")),
                ("Windows", claim.get("damage_windows")),
                ("Other damage", claim.get("damage_other")),
                ("Property secure", _fmt_yes_no(claim.get("property_secure"))),
                ("Repairs done", _fmt_yes_no(claim.get("repairs_done"))),
                ("Habitable", _fmt_yes_no(claim.get("property_habitable"))),
                ("Contents affected", _fmt_yes_no(claim.get("contents_affected"))),
                ("Contents total", _fmt_money(claim.get("contents_total_value"))),
              ])}
              {contents_html}
            </div>
            """
        )

    witness_html = ""
    for index, witness in enumerate(claim.get("witnesses") or [], start=1):
        witness_html += _person_dl(f"Witness {index}", "", witness)
    if not witness_html:
        witness_html = f"<p class='empty'>Witnesses present: {html.escape(_fmt_yes_no(claim.get('witnesses_present')))}</p>"

    other_html = ""
    for index, party in enumerate(claim.get("other_parties") or [], start=1):
        other_html += _person_dl(
            f"Other person {index}",
            "",
            party,
            extra=[
                ("Insurer", party.get("insurance_company")),
                ("Policy number", party.get("insurance_policy_number")),
                ("Claim number", party.get("insurance_claim_number")),
                ("Licence", party.get("licence_number")),
                ("Vehicle", " ".join(str(part) for part in (party.get("vehicle_registration"), party.get("vehicle_year"), party.get("vehicle_make"), party.get("vehicle_model")) if part) or None),
                ("Vehicle damage", party.get("vehicle_damage_areas")),
            ],
        )
    if not other_html:
        other_html = _dl([
            ("Anyone else involved", _fmt_yes_no(claim.get("others_involved"))),
            ("Name", claim.get("other_party_name")),
            ("Phone", claim.get("other_party_phone")),
            ("Email", claim.get("other_party_email")),
            ("Address", claim.get("other_party_address")),
            ("Vehicle registration", claim.get("other_party_vehicle_reg")),
            ("Insurance company", claim.get("other_party_insurer")),
        ])

    inner = f"""
    <div class="crumbs"><a href="/ui/dashboard">Dashboard</a> &gt; {html.escape(str(claim["claim_reference"]))}</div>
    <h1 class="page-title">{html.escape(str(claim["claim_reference"]))}</h1>
    <p class="page-sub">Claim {claim_id} · {_status_pill(current)}</p>
    {banners}
    <div class="card">
      <h2>Policy and claimant</h2>
      {_dl([
        ("Customer", f"{claim['customer_name']} ({claim['customer_email']})"),
        ("Phone", claim.get("customer_phone")),
        ("Policy", f"{claim['policy_number']} — {coverage}"),
        ("Insurance type", _claim_type_label(claim.get("claim_type"), claim)),
        ("Policy holder", holder_name),
        ("Title", claim.get("holder_title")),
        ("Company", claim.get("holder_company")),
        ("Address", holder_address),
        ("Preferred contact", claim.get("preferred_contact_method")),
        ("Email", claim.get("claimant_email") or claim.get("holder_email")),
        ("Phone", claim.get("claimant_phone") or claim.get("holder_phone")),
        ("GST registered", _fmt_yes_no(claim.get("gst_registered"))),
        ("ABN", claim.get("abn")),
        ("Submitted", _fmt_dt(claim["submission_date"])),
        ("Outcome date", _fmt_dt(claim["outcome_date"])),
        ("Priority", claim["priority_level"] if claim["priority_level"] is not None else 0),
        ("Fraud score", claim["fraud_risk_score"] if claim["fraud_risk_score"] is not None else 0),
        ("Estimated value", _fmt_money(claim.get("estimated_value") if claim.get("estimated_value") is not None else claim.get("cost"))),
      ])}
    </div>
    <div class="card">
      <h2>Incident details</h2>
      {_dl([
        ("Date", _fmt_date(claim.get("incident_date"))),
        ("Time", claim.get("incident_time")),
        ("Location", incident_address),
        ("What happened", claim.get("incident_description")),
        ("Reporter is policy holder", _fmt_yes_no(claim.get("is_policyholder"))),
        ("Relationship to holder", claim.get("relationship_to_holder")),
        ("Additional comments", claim.get("additional_comments")),
      ])}
    </div>
    {''.join(extra_cards)}
    <div class="card">
      <h2>Witnesses</h2>
      {witness_html}
    </div>
    <div class="card">
      <h2>Other people involved</h2>
      {other_html}
    </div>
    <div class="card">
      <h2>Police</h2>
      {_dl([
        ("Police report made", _fmt_yes_no(claim.get("police_involved"))),
        ("Report number", claim.get("police_report_number")),
        ("Date reported", _fmt_date(claim.get("police_reported_date"))),
        ("Charges laid", _fmt_yes_no(claim.get("charges_laid"))),
        ("Charge details", claim.get("charges_details")),
      ])}
    </div>
    <div class="card">
      <h2>Declaration</h2>
      {_dl([
        ("Confirmed accurate", _fmt_yes_no(claim.get("declaration_accepted"))),
        ("Name", claim.get("declaration_name")),
        ("Position held (if signing on behalf of someone)", claim.get("declaration_position")),
        ("Date", _fmt_date(claim.get("declaration_date"))),
      ])}
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
    {similar_match_html}
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


def _customer_claim_table(
    rows: list[dict[str, Any]],
    *,
    continue_draft: bool,
    open_id: Any = None,
) -> str:
    if not rows:
        return '<p class="empty">None yet.</p>'
    body = []
    for row in rows:
        claim_id = int(row["claim_id"])
        reference = html.escape(str(row["claim_reference"]))
        if continue_draft:
            ref_cell = f'<a href="/ui/claim?draft_id={claim_id}">{reference}</a>'
            percent = _draft_progress(row)
            when = _relative_time(row.get("submission_date"))
            action = f"""
              <div class="row-actions">
                <div class="progress" title="{percent}% complete"><span style="width:{percent}%"></span></div>
                <a href="/ui/claim?draft_id={claim_id}">Continue</a>
                <form method="post" action="/ui/drafts/{claim_id}/delete" onsubmit="return confirm('Delete this draft? This cannot be undone.');">
                  <button class="btn-link" type="submit">Delete</button>
                </form>
              </div>
            """
            if open_id and int(open_id) == claim_id:
                action = f"""
              <div class="row-actions">
                <div class="progress" title="{percent}% complete"><span style="width:{percent}%"></span></div>
                <strong>Editing now</strong>
              </div>
            """
            extra = f'<div class="hint">{html.escape(when)}</div>' if when else ""
            ref_cell = f"{ref_cell}{extra}"
        else:
            ref_cell = reference
            action = "—"
        body.append(
            f"""<tr>
              <td>{ref_cell}</td>
              <td>{html.escape(str(row.get("policy_number") or "—"))}</td>
              <td>{html.escape(_claim_type_label(row.get("claim_type"), row))}</td>
              <td>{html.escape(_fmt_date(row.get("incident_date")))}</td>
              <td>{_status_pill(str(row.get("status") or ""))}</td>
              <td>{action}</td>
            </tr>"""
        )
    return f"""
    <table class="data">
      <thead><tr><th>Reference</th><th>Policy</th><th>Type</th><th>Incident date</th><th>Status</th><th></th></tr></thead>
      <tbody>{''.join(body)}</tbody>
    </table>
    """


def _claimant_home_view(
    email: str,
    role: str,
    customer_id: int,
    *,
    error: str | None = None,
    success: dict | None = None,
    notice: str | None = None,
) -> HTMLResponse:
    banners = ""
    if error:
        banners += _banner("error", error)
    if notice:
        banners += _banner("success", notice)
    confetti = ""
    if success and not success.get("deleted"):
        banners += _banner("success", "Claim submitted. Keep the reference below for follow-up.")
        banners += f"""
        <div class="card">
          <h2>Submission details</h2>
          <dl class="result-grid">
            <dt>Claim ID</dt><dd>{html.escape(str(success.get("claim_id", "")))}</dd>
            <dt>Claim reference</dt><dd>{html.escape(str(success.get("claim_reference", "")))}</dd>
            <dt>Status</dt><dd>{html.escape(str(success.get("status", "")))}</dd>
            <dt>Files uploaded</dt><dd>{html.escape(str(success.get("files_uploaded", "")))}</dd>
          </dl>
        </div>
        """
        confetti = " confetti"

    profile = get_customer_profile(customer_id)
    first = html.escape(_first_name(profile, email))
    hello = html.escape(_day_greeting())
    tip = html.escape(_HOME_TIPS[date.today().toordinal() % len(_HOME_TIPS)])
    my_claims = list_customer_claims(customer_id)
    drafts = [row for row in my_claims if row.get("status") == "draft"]
    submitted = [row for row in my_claims if row.get("status") != "draft"]
    latest = drafts[0] if drafts else None
    resume = ""
    if latest:
        percent = _draft_progress(latest)
        resume = f"""
        <div class="resume">
          <div>
            <h2>Pick up where you left off</h2>
            <p>{html.escape(str(latest["claim_reference"]))} is about {percent}% complete. {_relative_time(latest.get("submission_date")) or "Ready when you are."}</p>
          </div>
          <a class="btn btn-primary" href="/ui/claim?draft_id={int(latest["claim_id"])}">Continue draft</a>
        </div>
        """
    drafts_body = _customer_claim_table(drafts, continue_draft=True)
    if not drafts:
        drafts_body = """
        <div class="empty-hero">
          <div class="mark" aria-hidden="true">✎</div>
          <p class="empty">Nothing in progress. When something happens, you can start a claim in a couple of minutes.</p>
        </div>
        """
    inner = f"""
    {banners}
    <section class="hero{confetti}">
      <h1>{hello}, {first}</h1>
      <p>This is your claims home. Start a new claim when you are ready, or pick up a draft you have already saved.</p>
      <a class="btn btn-primary" href="/ui/claim">Make a claim</a>
      <p class="tip">{tip}</p>
    </section>
    {resume}
    <div class="card">
      <h2>Your drafts</h2>
      <p class="section-help">Continue a saved draft, or delete one you no longer need.</p>
      {drafts_body}
    </div>
    <div class="card">
      <h2>Submitted claims</h2>
      {_customer_claim_table(submitted, continue_draft=False)}
    </div>
    """
    return _page("Home | Claim AI", _portal_chrome(email, role, inner, "home"))


def _claim_submit_view(
    email: str,
    role: str,
    customer_id: int,
    *,
    error: str | None = None,
    success: dict | None = None,
    draft: dict[str, Any] | None = None,
) -> HTMLResponse:
    banners = ""
    if error:
        banners += _banner("error", error)
    if success:
        saved = "Draft saved. You can come back and submit when you have more details." if success.get("status") == "draft" else "Claim submitted."
        banners += _banner("success", saved)
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
        policies = list_policies(customer_id)
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

    profile = get_customer_profile(customer_id)
    draft = draft or {}
    draft_id = int(draft["claim_id"]) if draft.get("claim_id") else ""
    delete_draft_btn = ""
    if draft_id:
        delete_draft_btn = f"""
        <form method="post" action="/ui/drafts/{draft_id}/delete" onsubmit="return confirm('Delete this draft? This cannot be undone.');">
          <button class="btn btn-danger" type="submit">Delete draft</button>
        </form>
        """
    form_fields = render_claim_form_fields(draft, policies, profile, email)
    inner = f"""
    <div class="crumbs"><a href="/ui/home">Home</a> &gt; Make a claim</div>
    <div class="page-head">
      <div>
        <h1 class="page-title">Make a claim</h1>
        <p class="page-sub">Choose motor vehicle or property insurance first. The form then follows the matching Allianz claim form. You can save a draft and add more later.</p>
      </div>
      <div class="row-actions">
        {delete_draft_btn}
        <a class="btn btn-primary" href="/ui/claim">New claim</a>
      </div>
    </div>
    {banners}
    <form class="card" id="claim-form" method="post" action="/ui/submit" enctype="multipart/form-data">
      {"<input type='hidden' name='claim_id' value='" + str(draft_id) + "'>" if draft_id else ""}
      {form_fields}
      <div class="form-actions">
        <a class="btn btn-secondary" href="/ui/home">Back to home</a>
        <button class="btn btn-secondary" type="submit" name="intent" value="draft" formnovalidate>Save as draft</button>
        <button class="btn btn-primary" type="submit" name="intent" value="submit">Submit claim</button>
      </div>
    </form>
    """
    return _page("Make a claim | Claim AI", _portal_chrome(email, role, inner, "claim"))


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
    doc = get_document(doc_id)
    try:
        downloaded = await download_claim_document(doc_id)
    except Exception as exc:
        if doc and doc.get("claim_id"):
            claim = get_claim(int(doc["claim_id"]))
            if claim is not None:
                return _claim_detail_view(
                    auth["email"], auth["role"], claim,
                    error=f"Could not download file: {exc}",
                )
        return _dashboard_view(auth["email"], auth["role"], error=f"Could not download file: {exc}")
    if downloaded is None:
        return _dashboard_view(auth["email"], auth["role"], error="Document not found.")
    data, filename, media_type = downloaded
    return evidence_download_response(data, filename, media_type)


@router.get("/my-documents/{doc_id}")
async def download_my_document(request: Request, doc_id: int):
    auth = _require_role(request, "claimant")
    if isinstance(auth, RedirectResponse):
        return auth
    if not customer_owns_claim_document(doc_id, auth["id"]):
        return _claimant_home_view(auth["email"], auth["role"], auth["id"], error="Document not found.")
    try:
        downloaded = await download_claim_document(doc_id)
    except Exception as exc:
        return _claimant_home_view(
            auth["email"], auth["role"], auth["id"],
            error=f"Could not download file: {exc}",
        )
    if downloaded is None:
        return _claimant_home_view(auth["email"], auth["role"], auth["id"], error="Document not found.")
    data, filename, media_type = downloaded
    return evidence_download_response(data, filename, media_type)


@router.get("/home", response_class=HTMLResponse)
def claimant_home(request: Request, submitted: int | None = None, deleted: str | None = None):
    auth = _require_role(request, "claimant")
    if isinstance(auth, RedirectResponse):
        return auth
    success = None
    notice = None
    if deleted:
        notice = f"Draft {deleted} was deleted."
    if submitted:
        success = {
            "claim_id": request.query_params.get("id", ""),
            "claim_reference": request.query_params.get("ref", ""),
            "status": "submitted",
            "files_uploaded": request.query_params.get("files", ""),
        }
    return _claimant_home_view(
        auth["email"], auth["role"], auth["id"],
        success=success,
        notice=notice,
    )


@router.post("/drafts/{claim_id}/delete")
async def delete_draft_page(request: Request, claim_id: int):
    auth = _require_role(request, "claimant")
    if isinstance(auth, RedirectResponse):
        return auth
    try:
        result = await delete_customer_draft(claim_id, auth["id"])
    except ClaimSubmitError as exc:
        return _claimant_home_view(auth["email"], auth["role"], auth["id"], error=str(exc))
    ref = quote(str(result.get("claim_reference") or "draft"))
    return RedirectResponse(f"/ui/home?deleted={ref}", status_code=303)


@router.get("/claim", response_class=HTMLResponse)
def claim_get(request: Request, draft_id: int | None = None, saved: int | None = None):
    auth = _require_role(request, "claimant")
    if isinstance(auth, RedirectResponse):
        return auth
    draft = None
    error = None
    success = None
    if draft_id is not None:
        draft = get_customer_claim(draft_id, auth["id"])
        if draft is None or draft.get("status") != "draft":
            draft = None
            error = "That draft was not found."
        elif saved:
            success = {
                "claim_id": draft["claim_id"],
                "claim_reference": draft["claim_reference"],
                "status": draft["status"],
                "files_uploaded": 0,
            }
    return _claim_submit_view(
        auth["email"], auth["role"], auth["id"],
        draft=draft,
        error=error,
        success=success,
    )


def _form_text(form: Any, key: str) -> str | None:
    value = form.get(key)
    if value is None or hasattr(value, "filename"):
        return None
    text = str(value).strip()
    return text or None


@router.post("/submit", response_class=HTMLResponse)
async def claim_submit(request: Request, db: AsyncSession = Depends(get_db)):
    auth = _require_role(request, "claimant")
    if isinstance(auth, RedirectResponse):
        return auth

    form = await request.form()
    files = [item for item in form.getlist("files") if getattr(item, "filename", None)]
    policy_raw = _form_text(form, "policy_id")
    claim_id_raw = _form_text(form, "claim_id")
    try:
        policy_id = int(policy_raw) if policy_raw else None
        claim_id = int(claim_id_raw) if claim_id_raw else None
    except ValueError:
        return _claim_submit_view(
            auth["email"], auth["role"], auth["id"],
            error="Choose a valid policy.",
        )

    user = {"sub": str(auth["id"]), "role": auth["role"], "email": auth["email"]}
    payload = payload_from_form(form)
    try:
        result = await submit_claim(
            db=db,
            user=user,
            policy_id=policy_id,
            files=files,
            intent=_form_text(form, "intent") or "submit",
            claim_id=claim_id,
            **payload,
        )
    except ClaimSubmitError as exc:
        posted = posted_draft_from_payload(payload, policy_id, claim_id)
        return _claim_submit_view(
            auth["email"], auth["role"], auth["id"],
            error=str(exc),
            draft=posted,
        )
    if result.get("status") == "draft":
        return RedirectResponse(
            f"/ui/claim?draft_id={result['claim_id']}&saved=1",
            status_code=303,
        )
    return RedirectResponse(
        "/ui/home?submitted=1"
        f"&id={result['claim_id']}"
        f"&ref={quote(str(result['claim_reference']))}"
        f"&files={result['files_uploaded']}",
        status_code=303,
    )
