"""HTML page for testing Azure Blob Storage uploads.

Mounted on the main app at /ui/storage. Temporary test UI — Vue will not use this.
"""

from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

from app.services.storage_service import (
    connection_string_configured,
    containers_public_json,
    list_container_blobs as list_blobs,
    upload_to_container as upload_blob,
)

router = APIRouter(prefix="/ui/storage", include_in_schema=False)


INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Blob Storage Test</title>
  <style>
    * { box-sizing: border-box; }
    body {
      font-family: system-ui, -apple-system, sans-serif;
      max-width: 720px;
      margin: 2rem auto;
      padding: 0 1rem;
      color: #1a1a1a;
      background: #f8f9fb;
    }
    h1 { font-size: 1.5rem; margin-bottom: 1rem; }
    nav {
      display: flex;
      gap: 0.5rem;
      margin-bottom: 1.25rem;
      flex-wrap: wrap;
    }
    nav button {
      background: #fff;
      color: #334155;
      border: 1px solid #cbd5e1;
      border-radius: 999px;
      padding: 0.45rem 1rem;
      font-size: 0.875rem;
      cursor: pointer;
    }
    nav button.active {
      background: #2563eb;
      color: #fff;
      border-color: #2563eb;
    }
    .meta { color: #555; font-size: 0.9rem; margin-bottom: 1.5rem; }
    #dropzone {
      border: 2px dashed #94a3b8;
      border-radius: 12px;
      padding: 2.5rem 1rem;
      text-align: center;
      background: #fff;
      cursor: pointer;
      transition: border-color 0.15s, background 0.15s;
    }
    #dropzone.dragover {
      border-color: #2563eb;
      background: #eff6ff;
    }
    #dropzone p { margin: 0.25rem 0; }
    #dropzone .hint { color: #64748b; font-size: 0.875rem; }
    #file-input { display: none; }
    #preview {
      margin-top: 1rem;
      display: none;
      background: #fff;
      border-radius: 12px;
      padding: 1rem;
    }
    #preview img,
    #preview video {
      max-width: 100%;
      max-height: 240px;
      border-radius: 8px;
      display: block;
      margin-bottom: 0.75rem;
    }
    #preview .pdf-icon {
      width: 64px;
      height: 64px;
      background: #fee2e2;
      color: #991b1b;
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 700;
      font-size: 0.75rem;
      margin-bottom: 0.75rem;
    }
    button.upload-btn {
      background: #2563eb;
      color: #fff;
      border: none;
      border-radius: 8px;
      padding: 0.6rem 1.2rem;
      font-size: 0.95rem;
      cursor: pointer;
    }
    button.upload-btn:disabled { opacity: 0.5; cursor: not-allowed; }
    #status {
      margin-top: 1rem;
      padding: 0.75rem 1rem;
      border-radius: 8px;
      display: none;
    }
    #status.ok { display: block; background: #dcfce7; color: #166534; }
    #status.err { display: block; background: #fee2e2; color: #991b1b; }
    #status a { color: inherit; word-break: break-all; }
    section { margin-top: 2rem; }
    section h2 { font-size: 1.1rem; }
    #blob-list { list-style: none; padding: 0; margin: 0; }
    #blob-list li {
      background: #fff;
      border-radius: 8px;
      padding: 0.6rem 0.8rem;
      margin-bottom: 0.5rem;
      font-size: 0.875rem;
      word-break: break-all;
    }
    #blob-list a { color: #2563eb; }
  </style>
</head>
<body>
  <h1>Blob Storage Test</h1>

  <nav id="nav"></nav>

  <p class="meta">Container: <strong id="container-name"></strong></p>

  <div id="dropzone">
    <p><strong id="drop-label"></strong></p>
    <p class="hint" id="drop-hint"></p>
    <input id="file-input" type="file" />
  </div>

  <div id="preview">
    <div id="preview-media"></div>
    <p id="file-name"></p>
    <button class="upload-btn" id="upload-btn" type="button">Upload to blob storage</button>
  </div>

  <div id="status"></div>

  <section>
    <h2 id="list-heading">Blobs in container</h2>
    <ul id="blob-list"><li>Loading…</li></ul>
  </section>

  <script>
    const CONTAINERS = __CONTAINERS_JSON__;

    const nav = document.getElementById("nav");
    const dropzone = document.getElementById("dropzone");
    const fileInput = document.getElementById("file-input");
    const preview = document.getElementById("preview");
    const previewMedia = document.getElementById("preview-media");
    const fileNameEl = document.getElementById("file-name");
    const uploadBtn = document.getElementById("upload-btn");
    const statusEl = document.getElementById("status");
    const blobList = document.getElementById("blob-list");
    const containerNameEl = document.getElementById("container-name");
    const dropLabelEl = document.getElementById("drop-label");
    const dropHintEl = document.getElementById("drop-hint");
    const listHeadingEl = document.getElementById("list-heading");

    let selectedFile = null;
    let previewObjectUrl = null;
    let activeKey = "images";

    function currentConfig() {
      return CONTAINERS[activeKey];
    }

    function formatSize(bytes) {
      if (bytes < 1024) return `${bytes} B`;
      if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
      return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    }

    function errorMessage(data, fallback) {
      if (!data || !data.detail) return fallback;
      if (typeof data.detail === "string") return data.detail;
      if (Array.isArray(data.detail)) {
        return data.detail.map((item) => item.msg || String(item)).join(", ");
      }
      return fallback;
    }

    function setStatus(message, ok) {
      statusEl.className = ok ? "ok" : "err";
      statusEl.innerHTML = message;
    }

    function clearStatus() {
      statusEl.className = "";
      statusEl.innerHTML = "";
    }

    function revokePreviewUrl() {
      if (previewObjectUrl) {
        URL.revokeObjectURL(previewObjectUrl);
        previewObjectUrl = null;
      }
    }

    function clearSelection() {
      selectedFile = null;
      revokePreviewUrl();
      preview.style.display = "none";
      previewMedia.innerHTML = "";
      fileInput.value = "";
    }

    function fileMatchesContainer(file, config) {
      if (!file) return false;
      if (file.type && config.allowed_types.includes(file.type)) return true;
      const name = (file.name || "").toLowerCase();
      if (config.key === "images") return /\\.(jpe?g|png|gif|webp|bmp)$/i.test(name);
      if (config.key === "videos") return /\\.(mp4|webm|mov|avi)$/i.test(name);
      if (config.key === "pds-policies") return name.endsWith(".pdf");
      return false;
    }

    function renderPreview(file) {
      previewMedia.innerHTML = "";
      revokePreviewUrl();
      previewObjectUrl = URL.createObjectURL(file);

      if (activeKey === "images") {
        const img = document.createElement("img");
        img.alt = "Preview";
        img.src = previewObjectUrl;
        previewMedia.appendChild(img);
      } else if (activeKey === "videos") {
        const video = document.createElement("video");
        video.controls = true;
        video.src = previewObjectUrl;
        previewMedia.appendChild(video);
      } else {
        const icon = document.createElement("div");
        icon.className = "pdf-icon";
        icon.textContent = "PDF";
        previewMedia.appendChild(icon);
      }
    }

    function pickFile(file) {
      const config = currentConfig();
      if (!fileMatchesContainer(file, config)) {
        setStatus(`Please select a valid file for ${config.label} (${config.hint}).`, false);
        return;
      }
      selectedFile = file;
      renderPreview(file);
      fileNameEl.textContent = `${file.name} (${formatSize(file.size)})`;
      preview.style.display = "block";
      clearStatus();
    }

    function renderNav() {
      nav.innerHTML = Object.values(CONTAINERS)
        .map((config) =>
          `<button type="button" data-key="${config.key}" class="${config.key === activeKey ? "active" : ""}">${config.label}</button>`
        )
        .join("");

      nav.querySelectorAll("button").forEach((button) => {
        button.addEventListener("click", () => switchContainer(button.dataset.key));
      });
    }

    function applyContainerUi() {
      const config = currentConfig();
      dropLabelEl.textContent = config.drop_label;
      dropHintEl.textContent = `or click to choose a file (${config.hint})`;
      fileInput.accept = config.accept;
      listHeadingEl.textContent = `Blobs in ${config.label.toLowerCase()} container`;
      clearSelection();
      clearStatus();
      loadBlobs();
    }

    function switchContainer(key) {
      if (!CONTAINERS[key] || key === activeKey) return;
      activeKey = key;
      renderNav();
      applyContainerUi();
    }

    dropzone.addEventListener("click", (event) => {
      if (event.target === fileInput) return;
      fileInput.click();
    });
    fileInput.addEventListener("click", (event) => event.stopPropagation());
    fileInput.addEventListener("change", (event) => pickFile(event.target.files[0]));

    dropzone.addEventListener("dragover", (event) => {
      event.preventDefault();
      dropzone.classList.add("dragover");
    });
    dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
    dropzone.addEventListener("drop", (event) => {
      event.preventDefault();
      dropzone.classList.remove("dragover");
      pickFile(event.dataTransfer.files[0]);
    });

    uploadBtn.addEventListener("click", async () => {
      if (!selectedFile) return;
      uploadBtn.disabled = true;
      clearStatus();

      const form = new FormData();
      form.append("file", selectedFile);

      try {
        const res = await fetch(`/ui/storage/api/${activeKey}/upload`, { method: "POST", body: form });
        const data = await res.json();
        if (!res.ok) throw new Error(errorMessage(data, "Upload failed"));
        setStatus(
          `Uploaded as <strong>${data.blob_name}</strong><br>` +
          `<a href="${data.url}" target="_blank" rel="noopener">${data.url}</a>`,
          true
        );
        clearSelection();
        await loadBlobs();
      } catch (err) {
        setStatus(err.message, false);
      } finally {
        uploadBtn.disabled = false;
      }
    });

    async function loadBlobs() {
      const config = currentConfig();
      blobList.innerHTML = "<li>Loading…</li>";
      try {
        const res = await fetch(`/ui/storage/api/${activeKey}/blobs`);
        const data = await res.json();
        if (!res.ok) throw new Error(errorMessage(data, "Could not load blob list"));
        containerNameEl.textContent = data.container;
        if (!data.items.length) {
          blobList.innerHTML = `<li>${config.empty_label}</li>`;
          return;
        }
        blobList.innerHTML = data.items
          .slice()
          .reverse()
          .map((item) =>
            `<li><a href="${item.url}" target="_blank" rel="noopener">${item.name}</a></li>`
          )
          .join("");
      } catch (err) {
        blobList.innerHTML = `<li>${err.message}</li>`;
      }
    }

    renderNav();
    applyContainerUi();
  </script>
</body>
</html>
"""


@router.get("/", response_class=HTMLResponse)
def index() -> str:
    return INDEX_HTML.replace("__CONTAINERS_JSON__", containers_public_json())


@router.get("/api/{container_key}/blobs")
async def blobs(container_key: str) -> dict[str, Any]:
    if not connection_string_configured():
        raise HTTPException(503, "AZURE_STORAGE_CONNECTION_STRING is not set")
    try:
        return await list_blobs(container_key)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Could not list blobs: {exc}") from exc


@router.post("/api/{container_key}/upload")
async def upload(container_key: str, file: UploadFile = File(...)) -> JSONResponse:
    if not connection_string_configured():
        raise HTTPException(503, "AZURE_STORAGE_CONNECTION_STRING is not set")
    try:
        result = await upload_blob(
            container_key,
            file.filename,
            file.content_type,
            await file.read(),
        )
    except ValueError as exc:
        status = 404 if str(exc).startswith("Unknown container") else 400
        raise HTTPException(status, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Upload failed: {exc}") from exc
    return JSONResponse(result)
