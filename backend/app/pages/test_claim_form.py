"""Minimal claim-creation form for manual pipeline testing.

Only asks for what the pipeline actually needs: a claimant (existing, or a
throwaway new one), a product (so retrieval knows motor vs. home), an
incident description (the claimant's own account - what Call 2 compares
Call 1's photo read against), and photos. Everything else on the real
Claim/claim_form flow is skipped; this is scaffolding, not the real
submission form.

Photos are picked before the claim exists (staged client-side) and
uploaded one at a time - with visible per-file progress - right after the
claim is created, as a single "Create claim" submit. The form then resets
for the next test claim, keeping the success message (with a link to
/ui/orchestration-test) visible above it.

Mounted on the main app at /ui/test-claim-form. Temporary test UI.
"""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.models import Claim, ClaimDocument, Customer, Policy, Product
from app.connectors.db import get_db
from app.connectors.storage import upload_image
from app.pages.ui_session import require_ui_role
from app.services.auth_service import hash_password
from app.services.claim_form import is_plausible_incident_heuristic, is_plausible_incident_model
from app.services.claim_service import generate_claim_reference
from app.services.damage_description_services import IMAGE_FILE_TYPES
from app.services.image_similarity_service import store_phash

router = APIRouter(prefix="/ui/test-claim-form", include_in_schema=False)

MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB


def _customer_options_html(customers: list[Customer]) -> str:
    return "".join(f'<option value="{c.customer_id}">{c.name} ({c.email})</option>' for c in customers)


INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Test Claim Form</title>
  <style>
    * { box-sizing: border-box; }
    body {
      font-family: system-ui, -apple-system, sans-serif;
      max-width: 520px;
      margin: 2rem auto;
      padding: 0 1rem 3rem;
      color: #1a1a1a;
      background: #f8f9fb;
    }
    h1 { font-size: 1.5rem; margin-bottom: 0.25rem; }
    p.meta { color: #555; font-size: 0.9rem; margin-bottom: 1.5rem; }
    .panel { background: #fff; border-radius: 10px; padding: 1.2rem; margin-bottom: 1rem; }
    .panel h2 { font-size: 0.95rem; margin: 0 0 0.8rem; }
    label { display: block; font-size: 0.85rem; font-weight: 600; margin: 0.7rem 0 0.3rem; }
    input[type="text"], input[type="email"], input[type="tel"], select, textarea {
      width: 100%; padding: 0.55rem 0.65rem; border: 1px solid #cbd5e1;
      border-radius: 8px; font-size: 0.9rem; background: #fff; font-family: inherit;
    }
    textarea { min-height: 90px; resize: vertical; }
    .toggle { display: flex; gap: 0.5rem; margin-top: 0.3rem; }
    .toggle button {
      flex: 1; background: #fff; color: #334155; border: 1px solid #cbd5e1;
      border-radius: 8px; padding: 0.5rem; font-size: 0.85rem; cursor: pointer;
    }
    .toggle button.active { background: #2563eb; color: #fff; border-color: #2563eb; }
    #new-claimant-fields, #existing-claimant-field { display: none; }
    #new-claimant-fields.show, #existing-claimant-field.show { display: block; }
    button.submit-btn {
      margin-top: 1.1rem; background: #2563eb; color: #fff; border: none;
      border-radius: 8px; padding: 0.6rem 1.4rem; font-size: 0.95rem; cursor: pointer; width: 100%;
    }
    button.submit-btn:disabled { opacity: 0.5; cursor: not-allowed; }
    #status { margin-top: 1rem; padding: 0.75rem 1rem; border-radius: 8px; display: none; font-size: 0.85rem; }
    #status.err { display: block; background: #fee2e2; color: #991b1b; }
    #status.ok { display: block; background: #dcfce7; color: #166534; }
    #status a { color: #166534; font-weight: 700; }
    #file-list { margin-top: 0.5rem; display: flex; flex-direction: column; gap: 0.3rem; }
    .file-row {
      display: flex; justify-content: space-between; align-items: center;
      background: #f1f5f9; border-radius: 6px; padding: 0.4rem 0.6rem; font-size: 0.8rem;
    }
    .file-row .file-status { font-weight: 700; display: flex; align-items: center; gap: 0.4rem; }
    .remove-file-btn {
      background: none; border: none; color: #94a3b8; font-size: 1rem; line-height: 1;
      cursor: pointer; padding: 0 0.15rem;
    }
    .remove-file-btn:hover { color: #dc2626; }
    .file-row.uploading .file-status { color: #2563eb; }
    .file-row.done .file-status { color: #16a34a; }
    .file-row.error .file-status { color: #dc2626; }
  </style>
</head>
<body>
  <h1>Test Claim Form</h1>
  <p class="meta">Minimal claim creation for manual pipeline testing - only the fields the pipeline actually needs. Pick an existing claimant or create a throwaway one, choose a product, describe the incident, pick photos, then submit.</p>

  <div class="panel">
    <h2>Claimant</h2>
    <div class="toggle">
      <button type="button" id="toggle-existing" class="active">Existing claimant</button>
      <button type="button" id="toggle-new">New claimant</button>
    </div>

    <div id="existing-claimant-field" class="show">
      <label for="customer_id">Claimant</label>
      <select id="customer_id">__CUSTOMER_OPTIONS__</select>
    </div>

    <div id="new-claimant-fields">
      <label for="new_name">Name</label>
      <input type="text" id="new_name" placeholder="Test Claimant" />
      <label for="new_email">Email</label>
      <input type="email" id="new_email" placeholder="unique@example.com" />
      <label for="new_phone">Phone (optional)</label>
      <input type="tel" id="new_phone" placeholder="" />
    </div>

    <label for="product_id">Product</label>
    <select id="product_id">__PRODUCT_OPTIONS__</select>

    <label for="incident_description">Incident description (claimant's own account)</label>
    <textarea id="incident_description" placeholder="Describe what happened, as the claimant would tell it..."></textarea>

    <label for="photo-input">Photos (click "Choose Files" again to add more - selections add up, they don't replace)</label>
    <input type="file" id="photo-input" accept="image/jpeg,image/png" multiple />
    <div id="file-list"></div>

    <button class="submit-btn" id="create-btn" type="button">Create claim</button>
    <div id="status"></div>
  </div>

  <script>
    const toggleExisting = document.getElementById("toggle-existing");
    const toggleNew = document.getElementById("toggle-new");
    const existingField = document.getElementById("existing-claimant-field");
    const newFields = document.getElementById("new-claimant-fields");
    const statusEl = document.getElementById("status");
    const createBtn = document.getElementById("create-btn");
    const photoInput = document.getElementById("photo-input");
    const fileListEl = document.getElementById("file-list");
    const incidentField = document.getElementById("incident_description");
    const productField = document.getElementById("product_id");
    const customerField = document.getElementById("customer_id");
    const newNameField = document.getElementById("new_name");
    const newEmailField = document.getElementById("new_email");
    const newPhoneField = document.getElementById("new_phone");

    let mode = "existing";
    // {file, status: "pending" | "uploading" | "done" | "error"}[] - accumulates
    // across multiple "Choose Files" interactions rather than being replaced by
    // the native input's own (single-selection-session) FileList each time.
    let stagedFiles = [];

    function setMode(next) {
      mode = next;
      toggleExisting.classList.toggle("active", mode === "existing");
      toggleNew.classList.toggle("active", mode === "new");
      existingField.classList.toggle("show", mode === "existing");
      newFields.classList.toggle("show", mode === "new");
    }
    toggleExisting.addEventListener("click", () => setMode("existing"));
    toggleNew.addEventListener("click", () => setMode("new"));

    function setStatus(html, cls) {
      statusEl.className = cls;
      statusEl.innerHTML = html;
    }

    function errorMessage(data, fallback) {
      if (!data || !data.detail) return fallback;
      if (typeof data.detail === "string") return data.detail;
      return fallback;
    }

    function escapeHtml(str) {
      const div = document.createElement("div");
      div.textContent = str;
      return div.innerHTML;
    }

    function renderFileList() {
      if (!stagedFiles.length) { fileListEl.innerHTML = ""; return; }
      fileListEl.innerHTML = stagedFiles
        .map((entry, i) => {
          const icon = entry.status === "done" ? "✓" : entry.status === "uploading" ? "…" : entry.status === "error" ? "✗" : "";
          const removable = entry.status === "pending";
          const removeBtn = removable ? `<button type="button" class="remove-file-btn" data-index="${i}" title="Remove">&times;</button>` : "";
          return `<div class="file-row ${entry.status}"><span>${escapeHtml(entry.file.name)}</span><span class="file-status">${icon}${removeBtn}</span></div>`;
        })
        .join("");
      fileListEl.querySelectorAll(".remove-file-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          stagedFiles.splice(parseInt(btn.dataset.index, 10), 1);
          renderFileList();
        });
      });
    }

    photoInput.addEventListener("change", () => {
      // Each picker interaction adds to the staged batch instead of replacing
      // it - opening "Choose Files" a second time used to silently drop
      // whatever was picked the first time.
      const existingKeys = new Set(stagedFiles.map((e) => `${e.file.name}:${e.file.size}:${e.file.lastModified}`));
      for (const file of photoInput.files) {
        const key = `${file.name}:${file.size}:${file.lastModified}`;
        if (!existingKeys.has(key)) {
          stagedFiles.push({ file, status: "pending" });
          existingKeys.add(key);
        }
      }
      photoInput.value = ""; // clear so the same file can be re-picked, and the next selection is treated as an addition
      renderFileList();
    });

    function resetForm() {
      setMode("existing");
      customerField.selectedIndex = 0;
      productField.selectedIndex = 0;
      incidentField.value = "";
      newNameField.value = "";
      newEmailField.value = "";
      newPhoneField.value = "";
      photoInput.value = "";
      stagedFiles = [];
      fileListEl.innerHTML = "";
    }

    createBtn.addEventListener("click", async () => {
      setStatus("", "");
      const payload = {
        product_id: parseInt(productField.value, 10),
        incident_description: incidentField.value.trim(),
      };
      if (!payload.incident_description) {
        setStatus("Enter an incident description.", "err");
        return;
      }
      if (mode === "existing") {
        payload.customer_id = parseInt(customerField.value, 10);
      } else {
        payload.new_customer_name = newNameField.value.trim();
        payload.new_customer_email = newEmailField.value.trim();
        payload.new_customer_phone = newPhoneField.value.trim();
        if (!payload.new_customer_name || !payload.new_customer_email) {
          setStatus("New claimant needs at least a name and email.", "err");
          return;
        }
      }

      createBtn.disabled = true;
      try {
        const res = await fetch("/ui/test-claim-form/api/create", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(errorMessage(data, "Could not create claim"));
        const claimId = data.claim_id;

        for (const entry of stagedFiles) {
          entry.status = "uploading";
          renderFileList();
          const form = new FormData();
          form.append("files", entry.file);
          const uploadRes = await fetch(`/ui/test-claim-form/api/upload?claim_id=${claimId}`, { method: "POST", body: form });
          const uploadData = await uploadRes.json();
          entry.status = uploadRes.ok ? "done" : "error";
          renderFileList();
          if (!uploadRes.ok) {
            throw new Error(`Claim ${claimId} was created, but upload failed for ${entry.file.name}: ${errorMessage(uploadData, "upload error")}`);
          }
        }

        const runUrl = `/ui/orchestration-test?claim_id=${claimId}`;
        setStatus(
          `Created claim_id=${claimId} (policy_id=${data.policy_id}), uploaded ${stagedFiles.length} photo(s). ` +
          `<a href="${runUrl}" target="_blank" rel="noopener">Run pipeline &amp; view audit trail &rarr;</a>`,
          "ok"
        );
        resetForm();
      } catch (err) {
        setStatus(escapeHtml(err.message), "err");
      } finally {
        createBtn.disabled = false;
      }
    });
  </script>
</body>
</html>
"""


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, db: AsyncSession = Depends(get_db)):
    auth = require_ui_role(request, "assessor")
    if isinstance(auth, RedirectResponse):
        return auth

    customers = (await db.execute(select(Customer).order_by(Customer.customer_id))).scalars().all()
    products = (await db.execute(select(Product).order_by(Product.product_id))).scalars().all()

    product_options = "".join(
        f'<option value="{p.product_id}" data-insurance-type="{p.insurance_type}">{p.product_name}</option>'
        for p in products
    )

    html = INDEX_HTML
    html = html.replace("__CUSTOMER_OPTIONS__", _customer_options_html(customers))
    html = html.replace("__PRODUCT_OPTIONS__", product_options)
    # No-store: this test page's JS has changed under active development more
    # than once, and a cached copy silently running stale logic (e.g. an old
    # single-file upload handler) is a worse failure mode than an extra fetch.
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@router.post("/api/create")
async def create(request: Request, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    auth = require_ui_role(request, "assessor")
    if isinstance(auth, RedirectResponse):
        raise HTTPException(401, "Assessor sign-in required.")

    body = await request.json()
    product_id = body.get("product_id")
    incident_description = (body.get("incident_description") or "").strip()
    if not product_id or not incident_description:
        raise HTTPException(400, "product_id and incident_description are required.")

    # Same layered gate as the real claim form: free heuristic first, nano
    # model check only if that passes - rejects before any of Call 1/Call 2/
    # Generation ever run on this claim.
    if not is_plausible_incident_heuristic(incident_description):
        raise HTTPException(400, "Please provide a clearer description of what happened.")
    if not await asyncio.to_thread(is_plausible_incident_model, incident_description):
        raise HTTPException(400, "Please provide a clearer description of what happened.")

    product = await db.get(Product, product_id)
    if product is None:
        raise HTTPException(404, f"Unknown product_id: {product_id}")

    customer_id = body.get("customer_id")
    if customer_id:
        customer = await db.get(Customer, customer_id)
        if customer is None:
            raise HTTPException(404, f"Unknown customer_id: {customer_id}")
    else:
        name = (body.get("new_customer_name") or "").strip()
        email = (body.get("new_customer_email") or "").strip()
        phone = (body.get("new_customer_phone") or "").strip() or None
        if not name or not email:
            raise HTTPException(400, "new_customer_name and new_customer_email are required for a new claimant.")
        existing = (await db.execute(select(Customer).where(Customer.email == email))).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(409, f"A customer with email {email} already exists (customer_id={existing.customer_id}).")
        customer = Customer(
            name=name,
            email=email,
            phone=phone,
            hashed_password=hash_password(uuid.uuid4().hex),  # throwaway - test claimant, not a real login
        )
        db.add(customer)
        await db.flush()

    policy = (
        await db.execute(
            select(Policy).where(Policy.customer_id == customer.customer_id, Policy.product_id == product_id)
        )
    ).scalars().first()
    if policy is None:
        policy = Policy(
            customer_id=customer.customer_id,
            product_id=product_id,
            policy_number=f"TEST-{uuid.uuid4().hex[:10].upper()}",
            coverage_type=product.product_name,
        )
        db.add(policy)
        await db.flush()

    claim = Claim(
        claim_reference=generate_claim_reference(),
        customer_id=customer.customer_id,
        policy_id=policy.policy_id,
        insurance_type=product.insurance_type,
        incident_description=incident_description,
        claimant_name=customer.name,
        claimant_email=customer.email,
        claimant_phone=customer.phone,
    )
    db.add(claim)
    await db.commit()
    await db.refresh(claim)

    return JSONResponse({"claim_id": claim.claim_id, "policy_id": policy.policy_id, "customer_id": customer.customer_id})


@router.post("/api/upload")
async def upload(
    request: Request, claim_id: int, db: AsyncSession = Depends(get_db), files: list[UploadFile] = File(...)
) -> JSONResponse:
    auth = require_ui_role(request, "assessor")
    if isinstance(auth, RedirectResponse):
        raise HTTPException(401, "Assessor sign-in required.")

    claim = await db.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(404, f"claim_id={claim_id} not found")

    # Validate everything before uploading anything, so a bad file in the
    # batch doesn't leave a partial set of ClaimDocument rows behind.
    contents_by_file: list[tuple[UploadFile, bytes]] = []
    for file in files:
        if file.content_type not in IMAGE_FILE_TYPES:
            raise HTTPException(400, f"Unsupported file type: {file.content_type} ({file.filename})")
        contents = await file.read()
        if len(contents) > MAX_FILE_SIZE:
            raise HTTPException(400, f"File too large: {file.filename}")
        contents_by_file.append((file, contents))

    blob_names = []
    for file, contents in contents_by_file:
        blob_name = f"claim-{claim_id}/{uuid.uuid4()}-{file.filename}"
        await upload_image(blob_name, contents, content_type=file.content_type, overwrite=False)
        document = ClaimDocument(claim_id=claim_id, file_type=file.content_type, file_url=blob_name)
        db.add(document)
        await db.flush()
        await store_phash(db, document.doc_id, contents)
        blob_names.append(blob_name)
    await db.commit()
    return JSONResponse({"uploaded": True, "uploaded_count": len(blob_names), "blob_names": blob_names})
