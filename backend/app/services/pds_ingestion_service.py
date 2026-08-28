"""Parses a PDS PDF into clause-level chunks, embeds them, and upserts them
into the shared `pds_clauses` ChromaDB collection.

One-time, offline: run per product (not per claim) via
scripts/ingest_pds_documents.py. See
.claude/plans/stage0-pds-ingestion-retrieval.md for the design.

Chunking approach, tuned against the actual sample PDS documents:
- Headings are numbered ("4. Comprehensive cover", "4.1 Accidental loss or
  damage"); each heading + its body is one chunk — these are already
  atomic, single-topic units, so no overlap is needed.
- Tables (Excesses, Definitions, Limits, Levels of cover) are extracted
  separately from prose via pdfplumber's table bounding boxes, so table
  cell text isn't duplicated into the prose stream. Each table becomes its
  own chunk, tagged with the nearest preceding heading — on pages with more
  than one table under different sub-headings this tagging is approximate
  (uses the last heading seen so far on that page), which is an accepted
  simplification for now.
- The table-of-contents table and known non-coverage sections (motor PDS's
  "Insurance Schedule template", both PDS's appendices) are excluded from
  the corpus entirely — they're operational content, not coverage rules.
"""

from __future__ import annotations

import io
import re

import pdfplumber

from app.connectors.chromadb_store import get_pds_clauses_collection
from app.connectors.foundry import embed_texts
from app.connectors.storage import download_stored_blob

_SUB_HEADING = re.compile(r"^(\d+)\.(\d+)\s+(.+)$")
_TOP_HEADING = re.compile(r"^(\d+)\.\s+(.+)$")
_APPENDIX_HEADING = re.compile(r"^Appendix\s+[A-Z]\s*-\s*(.+)$", re.IGNORECASE)

_EXCLUDE_TITLE_KEYWORDS = ("schedule template", "schedule structure")

# Running page headers/footers repeat on every page and otherwise leak into
# whichever chunk happens to be open when the page breaks.
_BOILERPLATE_PATTERNS = [
    re.compile(r"^Illustrative sample - not an actual insurance product\s*\|\s*\d+$", re.IGNORECASE),
    re.compile(r"^[A-Z0-9 &]+\|[A-Z0-9 &]+\|[A-Z ]+$"),
    re.compile(r"^Southern Cross .* - Illustrative Sample.*$", re.IGNORECASE),
]

_MIN_CHUNK_BODY_LENGTH = 15


def _is_excluded_title(title: str) -> bool:
    lowered = title.lower()
    return any(keyword in lowered for keyword in _EXCLUDE_TITLE_KEYWORDS)


def _is_boilerplate(line: str) -> bool:
    return any(pattern.match(line) for pattern in _BOILERPLATE_PATTERNS)


def _table_is_toc(table: list[list[str | None]]) -> bool:
    if not table:
        return False
    header = [str(cell or "").strip().lower() for cell in table[0]]
    return "section" in header and "topic" in header


def _format_table_chunk(table: list[list[str | None]]) -> str:
    lines = [" | ".join(str(cell or "").strip() for cell in row) for row in table]
    return "\n".join(line for line in lines if line.strip(" |"))


def extract_chunks(pdf_bytes: bytes) -> list[dict]:
    """Parse a PDS PDF into a list of {section_ref, title, text} chunks."""
    chunks: list[dict] = []
    section_ref: str | None = None
    title: str | None = None
    body: list[str] = []
    excluded = False
    in_appendix = False  # one-way latch: once True, never reset (see below)
    last_top_level_ref: str | None = None

    def flush() -> None:
        nonlocal body
        if section_ref and body and not excluded:
            text = "\n".join(body).strip()
            if len(text) >= _MIN_CHUNK_BODY_LENGTH:
                chunks.append(
                    {
                        "section_ref": section_ref,
                        "title": title or "",
                        "text": f"{section_ref} {title}\n{text}".strip(),
                    }
                )
        body = []

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            tables = page.find_tables()
            table_bboxes = [t.bbox for t in tables]

            def outside_tables(obj: dict, _bboxes: list = table_bboxes) -> bool:
                x0, top, x1, bottom = obj.get("x0"), obj.get("top"), obj.get("x1"), obj.get("bottom")
                if x0 is None:
                    return True
                return not any(
                    x0 >= tx0 - 1 and x1 <= tx1 + 1 and top >= ttop - 1 and bottom <= tbottom + 1
                    for (tx0, ttop, tx1, tbottom) in _bboxes
                )

            prose = page.filter(outside_tables).extract_text() or ""

            for line in prose.split("\n"):
                line = line.strip()
                if not line or _is_boilerplate(line):
                    continue

                sub_match = _SUB_HEADING.match(line)
                top_match = None if sub_match else _TOP_HEADING.match(line)
                appendix_match = (
                    None if (sub_match or top_match) else _APPENDIX_HEADING.match(line)
                )

                # Once inside an appendix, its own numbered lists ("1. First
                # Notice of Loss...") are syntactically indistinguishable
                # from real top-level headings — don't let them re-open
                # heading detection and reset `excluded` back to False.
                if in_appendix:
                    continue

                if sub_match:
                    flush()
                    num, sub, heading_title = sub_match.groups()
                    section_ref, title = f"{num}.{sub}", heading_title
                    continue
                if top_match:
                    flush()
                    num, heading_title = top_match.groups()
                    section_ref, title = f"{num}.", heading_title
                    excluded = _is_excluded_title(heading_title)
                    last_top_level_ref = section_ref
                    continue
                if appendix_match:
                    flush()
                    section_ref, title = "Appendix", appendix_match.group(1)
                    excluded = True
                    in_appendix = True
                    continue

                if section_ref is not None:
                    body.append(line)

            if not excluded and not in_appendix:
                for table in (t.extract() for t in tables):
                    if not table or _table_is_toc(table):
                        continue
                    text = _format_table_chunk(table)
                    if text.strip():
                        chunks.append(
                            {
                                "section_ref": section_ref or last_top_level_ref or "",
                                "title": title or "",
                                "text": text,
                            }
                        )

        flush()

    return [c for c in chunks if c["text"].strip()]


def ingest_product_pds(*, pds_id: int, product_id: int, version: str, pdf_bytes: bytes) -> int:
    """Chunk, embed, and upsert one PDS document. Returns the chunk count."""
    chunks = extract_chunks(pdf_bytes)
    if not chunks:
        return 0

    texts = [c["text"] for c in chunks]
    embeddings = embed_texts(texts)
    ids = [f"pds-{pds_id}-{i}" for i in range(len(chunks))]
    metadatas = [
        {
            "pds_id": pds_id,
            "product_id": product_id,
            "version": version,
            "section_ref": c["section_ref"],
            "chunk_index": i,
        }
        for i, c in enumerate(chunks)
    ]

    collection = get_pds_clauses_collection()
    existing = collection.get(where={"pds_id": pds_id})
    if existing and existing.get("ids"):
        collection.delete(ids=existing["ids"])
    collection.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
    return len(chunks)


async def ingest_product_pds_from_blob(
    *, pds_id: int, product_id: int, version: str, file_url: str
) -> int:
    """Download a PDS from blob storage, then chunk/embed/upsert it."""
    pdf_bytes = await download_stored_blob(file_url)
    return ingest_product_pds(
        pds_id=pds_id, product_id=product_id, version=version, pdf_bytes=pdf_bytes
    )
