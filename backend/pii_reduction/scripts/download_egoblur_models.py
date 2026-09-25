"""Download EgoBlur Gen1 TorchScript models into pii_reduction/models/.

Gen1 weights are public on Hugging Face (projectaria/EgoBlur historical commit).
Gen2 Aria weights remain email-gated at https://www.projectaria.com/tools/egoblur —
drop them into models/ as ego_blur_*_gen2.jit if you obtain them.
"""

from __future__ import annotations

import sys
import urllib.request
import zipfile
from pathlib import Path

FACE_URL = (
    "https://huggingface.co/projectaria/EgoBlur/resolve/"
    "9c0b319ad09d0346e8294d7bf569593d3ab865c0/ego_blur_face.zip"
)
LP_URL = (
    "https://huggingface.co/projectaria/EgoBlur/resolve/"
    "9c0b319ad09d0346e8294d7bf569593d3ab865c0/ego_blur_lp.zip"
)


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {url} -> {dest} ...")
    urllib.request.urlretrieve(url, dest)  # noqa: S310 — fixed HF URLs
    print(f"  saved {dest.stat().st_size / 1e6:.1f} MB")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    models = root / "models"
    models.mkdir(parents=True, exist_ok=True)

    face_zip = models / "ego_blur_face.zip"
    lp_zip = models / "ego_blur_lp.zip"

    if not (models / "ego_blur_face.jit").is_file():
        _download(FACE_URL, face_zip)
        with zipfile.ZipFile(face_zip, "r") as zf:
            zf.extractall(models)
        print("Extracted face model")
    else:
        print("Face model already present")

    if not (models / "ego_blur_lp.jit").is_file():
        _download(LP_URL, lp_zip)
        with zipfile.ZipFile(lp_zip, "r") as zf:
            zf.extractall(models)
        print("Extracted LP model")
    else:
        print("LP model already present")

    face = models / "ego_blur_face.jit"
    lp = models / "ego_blur_lp.jit"
    ok = face.is_file() and lp.is_file()
    print(f"face={face.is_file()} lp={lp.is_file()}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
