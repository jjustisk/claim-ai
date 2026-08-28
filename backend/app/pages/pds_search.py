"""HTML page for manually testing PDS clause retrieval (Stage 0).

Type a damage description, pick a product, see the top-k clauses returned
by policy_retrieval_service.retrieve_clauses() with their distances.

Mounted on the main app at /ui/pds-search. Temporary test UI — Vue will not
use this; delete once the Decision LLM step consumes retrieval directly.
"""

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.connectors.db import get_sync_connection
from app.pages.ui_session import require_ui_role
from app.services.policy_retrieval_service import (
    DEFAULT_GAP_THRESHOLD,
    DEFAULT_MAX_K,
    retrieve_clauses,
)

router = APIRouter(prefix="/ui/pds-search", include_in_schema=False)


INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>PDS Retrieval Test</title>
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
    select, textarea, input[type="number"] {
      width: 100%;
      padding: 0.6rem 0.7rem;
      border: 1px solid #cbd5e1;
      border-radius: 8px;
      font-size: 0.95rem;
      background: #fff;
      font-family: inherit;
    }
    textarea { min-height: 90px; resize: vertical; }
    .row { display: flex; gap: 1rem; }
    .row > div { flex: 1; }
    button.search-btn {
      margin-top: 1.1rem;
      background: #2563eb;
      color: #fff;
      border: none;
      border-radius: 8px;
      padding: 0.6rem 1.4rem;
      font-size: 0.95rem;
      cursor: pointer;
    }
    button.search-btn:disabled { opacity: 0.5; cursor: not-allowed; }
    #status {
      margin-top: 1rem;
      padding: 0.75rem 1rem;
      border-radius: 8px;
      display: none;
    }
    #status.err { display: block; background: #fee2e2; color: #991b1b; }
    section { margin-top: 1.5rem; }
    .result {
      background: #fff;
      border-radius: 10px;
      padding: 0.9rem 1.1rem;
      margin-bottom: 0.75rem;
      border-left: 4px solid #2563eb;
    }
    .result .ref {
      font-size: 0.8rem;
      font-weight: 700;
      color: #2563eb;
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }
    .result .dist { float: right; color: #64748b; font-size: 0.8rem; font-weight: 400; }
    .result pre {
      white-space: pre-wrap;
      font-family: inherit;
      margin: 0.5rem 0 0;
      font-size: 0.9rem;
      line-height: 1.4;
    }
    #empty { color: #64748b; font-size: 0.9rem; }
  </style>
</head>
<body>
  <h1>PDS Retrieval Test</h1>
  <p class="meta">Manual test for Stage 0 retrieval — embeds the text below and queries ChromaDB scoped to the selected product.</p>

  <label for="product">Product</label>
  <select id="product"></select>

  <label for="text">Damage description</label>
  <textarea id="text" placeholder="e.g. Hail damage to the bonnet and roof of the vehicle"></textarea>

  <div class="row">
    <div>
      <label for="max_k">Max k</label>
      <input type="number" id="max_k" value="5" min="1" max="20" />
    </div>
    <div>
      <label for="gap_threshold">Gap threshold</label>
      <input type="number" id="gap_threshold" value="0.15" step="0.01" min="0" />
    </div>
  </div>

  <button class="search-btn" id="search-btn" type="button">Search</button>

  <div id="status"></div>

  <section>
    <div id="results"><p id="empty">No search yet.</p></div>
  </section>

  <script>
    const PRODUCTS = __PRODUCTS_JSON__;
    const productSelect = document.getElementById("product");
    const textInput = document.getElementById("text");
    const maxKInput = document.getElementById("max_k");
    const gapInput = document.getElementById("gap_threshold");
    const searchBtn = document.getElementById("search-btn");
    const statusEl = document.getElementById("status");
    const resultsEl = document.getElementById("results");

    productSelect.innerHTML = PRODUCTS.map(
      (p) => `<option value="${p.product_id}">${p.product_name}</option>`
    ).join("");

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

    async function runSearch() {
      const text = textInput.value.trim();
      if (!text) {
        setError("Enter a damage description first.");
        return;
      }
      clearError();
      searchBtn.disabled = true;
      resultsEl.innerHTML = "<p id=\\"empty\\">Searching…</p>";

      const params = new URLSearchParams({
        text,
        product_id: productSelect.value,
        max_k: maxKInput.value,
        gap_threshold: gapInput.value,
      });

      try {
        const res = await fetch(`/ui/pds-search/api/query?${params.toString()}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Search failed");

        if (!data.results.length) {
          resultsEl.innerHTML = "<p id=\\"empty\\">No results.</p>";
          return;
        }
        resultsEl.innerHTML = data.results
          .map(
            (r) => `
              <div class="result">
                <span class="ref">${escapeHtml(r.section_ref || "")}</span>
                <span class="dist">distance ${r.distance.toFixed(4)}</span>
                <pre>${escapeHtml(r.text)}</pre>
              </div>`
          )
          .join("");
      } catch (err) {
        setError(err.message);
        resultsEl.innerHTML = "";
      } finally {
        searchBtn.disabled = false;
      }
    }

    searchBtn.addEventListener("click", runSearch);
    textInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) runSearch();
    });
  </script>
</body>
</html>
"""


def _list_products() -> list[dict[str, Any]]:
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT product_id, product_name FROM product ORDER BY product_name")
            return [{"product_id": row[0], "product_name": row[1]} for row in cur.fetchall()]
    finally:
        conn.close()


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    auth = require_ui_role(request, "assessor")
    if isinstance(auth, RedirectResponse):
        return auth
    return INDEX_HTML.replace("__PRODUCTS_JSON__", json.dumps(_list_products()))


@router.get("/api/query")
def query(
    request: Request,
    text: str,
    product_id: int,
    max_k: int = DEFAULT_MAX_K,
    gap_threshold: float = DEFAULT_GAP_THRESHOLD,
) -> JSONResponse:
    auth = require_ui_role(request, "assessor")
    if isinstance(auth, RedirectResponse):
        raise HTTPException(401, "Assessor sign-in required.")
    if not text.strip():
        raise HTTPException(400, "text is required.")
    try:
        results = retrieve_clauses(
            text, product_id=product_id, max_k=max_k, gap_threshold=gap_threshold
        )
    except Exception as exc:
        raise HTTPException(500, f"Retrieval failed: {exc}") from exc
    return JSONResponse(
        {
            "results": [
                {
                    "section_ref": r["metadata"].get("section_ref"),
                    "distance": r["distance"],
                    "text": r["text"],
                }
                for r in results
            ]
        }
    )
