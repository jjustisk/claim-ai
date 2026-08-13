import re
import unicodedata
import html

CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
ZERO_WIDTH_RE = re.compile(r"[​-‏‪-‮⁠-⁯﻿]")
HTML_TAG_RE = re.compile(r"<[^>]*>")
WHITESPACE_RUN_RE = re.compile(r"\n{3,}")

INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", re.I),
    re.compile(r"disregard\s+(the\s+)?(above|previous)", re.I),
    re.compile(r"system\s*:", re.I),
    re.compile(r"you\s+are\s+now|act\s+as\s+(a|an)\s", re.I),
    re.compile(r"new\s+instructions\s*:", re.I),
    re.compile(r"<\|.*?\|>"),
    re.compile(r"###\s*(system|instruction)", re.I),
    re.compile(r"forget\s+(everything|all)\s+(you\s+know|above)", re.I),
]


def sanitize_free_text(text: str) -> str:
    t = unicodedata.normalize("NFKC", text)
    t = CONTROL_CHAR_RE.sub("", t)
    t = ZERO_WIDTH_RE.sub("", t)
    t = HTML_TAG_RE.sub("", t)
    t = html.escape(t, quote=False)
    for pattern in INJECTION_PATTERNS:
        t = pattern.sub("", t)
    t = WHITESPACE_RUN_RE.sub("\n\n", t)
    return t.strip()
