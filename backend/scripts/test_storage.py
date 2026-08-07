"""Local web UI for testing Azure Blob Storage image uploads.

Run from backend/:
    python scripts/test_storage.py

Then open http://127.0.0.1:8765
"""

import mimetypes
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

from app.config import settings
from app.storage import close_blob_service_client, list_images, upload_image

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await close_blob_service_client()


app = FastAPI(title="Storage Test UI", lifespan=lifespan)


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
    h1 { font-size: 1.5rem; margin-bottom: 0.25rem; }
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
    #preview img {
      max-width: 100%;
      max-height: 240px;
      border-radius: 8px;
      display: block;
      margin-bottom: 0.75rem;
    }
    button {
      background: #2563eb;
      color: #fff;
      border: none;
      border-radius: 8px;
      padding: 0.6rem 1.2rem;
      font-size: 0.95rem;
      cursor: pointer;
    }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
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
  <p class="meta">Container: <strong id="container-name"></strong></p>

  <div id="dropzone">
    <p><strong>Drag &amp; drop an image here</strong></p>
    <p class="hint">or click to choose a file (JPEG, PNG, GIF, WebP, BMP)</p>
    <input id="file-input" type="file" accept="image/*" />
  </div>

  <div id="preview">
    <img id="preview-img" alt="Preview" />
    <p id="file-name"></p>
    <button id="upload-btn" type="button">Upload to blob storage</button>
  </div>

  <div id="status"></div>

  <section>
    <h2>Recent uploads in container</h2>
    <ul id="blob-list"><li>Loading…</li></ul>
  </section>

  <script>
    const dropzone = document.getElementById("dropzone");
    const fileInput = document.getElementById("file-input");
    const preview = document.getElementById("preview");
    const previewImg = document.getElementById("preview-img");
    const fileNameEl = document.getElementById("file-name");
    const uploadBtn = document.getElementById("upload-btn");
    const statusEl = document.getElementById("status");
    const blobList = document.getElementById("blob-list");
    const containerNameEl = document.getElementById("container-name");

    let selectedFile = null;

    function isImageFile(file) {
      if (!file) return false;
      if (file.type && file.type.startsWith("image/")) return true;
      return /\.(jpe?g|png|gif|webp|bmp)$/i.test(file.name || "");
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

    function pickFile(file) {
      if (!isImageFile(file)) {
        setStatus("Please select an image file (JPEG, PNG, GIF, WebP, BMP).", false);
        return;
      }
      selectedFile = file;
      previewImg.src = URL.createObjectURL(file);
      fileNameEl.textContent = `${file.name} (${Math.round(file.size / 1024)} KB)`;
      preview.style.display = "block";
      clearStatus();
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
        const res = await fetch("/upload", { method: "POST", body: form });
        const data = await res.json();
        if (!res.ok) throw new Error(errorMessage(data, "Upload failed"));
        setStatus(
          `Uploaded as <strong>${data.blob_name}</strong><br>` +
          `<a href="${data.url}" target="_blank" rel="noopener">${data.url}</a>`,
          true
        );
        selectedFile = null;
        preview.style.display = "none";
        fileInput.value = "";
        await loadBlobs();
      } catch (err) {
        setStatus(err.message, false);
      } finally {
        uploadBtn.disabled = false;
      }
    });

    async function loadBlobs() {
      try {
        const res = await fetch("/images");
        const data = await res.json();
        if (!res.ok) throw new Error(errorMessage(data, "Could not load blob list"));
        containerNameEl.textContent = data.container;
        if (!data.items.length) {
          blobList.innerHTML = "<li>No images yet.</li>";
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

    loadBlobs();
  </script>
</body>
</html>
"""


def _guess_content_type(filename: str, reported: str | None) -> str:
    if reported and reported in ALLOWED_TYPES:
        return reported
    guessed, _ = mimetypes.guess_type(filename)
    return guessed if guessed in ALLOWED_TYPES else "application/octet-stream"


def _blob_url(blob_name: str) -> str:
    # Connection string format: ...AccountName=xxx;AccountKey=...
    account_name = ""
    for part in settings.azure_storage_connection_string.split(";"):
        if part.startswith("AccountName="):
            account_name = part.split("=", 1)[1]
            break
    container = settings.azure_storage_images_container_name
    return f"https://{account_name}.blob.core.windows.net/{container}/{blob_name}"


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return INDEX_HTML


@app.get("/images")
async def get_images() -> dict:
    if not settings.azure_storage_connection_string:
        raise HTTPException(503, "AZURE_STORAGE_CONNECTION_STRING is not set")
    try:
        names = await list_images()
    except Exception as exc:
        raise HTTPException(500, f"Could not list blobs: {exc}") from exc
    return {
        "container": settings.azure_storage_images_container_name,
        "items": [{"name": name, "url": _blob_url(name)} for name in names],
    }


@app.post("/upload")
async def upload(file: UploadFile = File(...)) -> JSONResponse:
    if not settings.azure_storage_connection_string:
        raise HTTPException(503, "AZURE_STORAGE_CONNECTION_STRING is not set")

    content_type = _guess_content_type(file.filename or "image.jpg", file.content_type)
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(
            400,
            f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_TYPES))}",
        )

    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")

    original = Path(file.filename or "image.jpg").name
    blob_name = f"test-uploads/{uuid.uuid4().hex}-{original}"

    try:
        url = await upload_image(blob_name, data, content_type=content_type)
    except Exception as exc:
        raise HTTPException(500, f"Upload failed: {exc}") from exc

    return JSONResponse({"blob_name": blob_name, "url": url})


if __name__ == "__main__":
    print("Storage test UI → http://127.0.0.1:8765")
    print(f"Container: {settings.azure_storage_images_container_name}")
    uvicorn.run(app, host="127.0.0.1", port=8765)
