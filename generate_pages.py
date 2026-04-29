"""
generate_pages.py — Convert all PDF pages to PNG images.

Run once locally. Outputs to static/pages/.
Requires Poppler (same as ingest_vision.py).

Usage: python generate_pages.py
"""

import os
from pathlib import Path
from pdf2image import convert_from_path

POPPLER_PATH = r"K:\Poppler\poppler-25.12.0\Library\bin"  # same as ingest_vision.py

PDF_FILES = [
    "files/owner-manual.pdf",
    "files/quick-start-guide.pdf",
    "files/selection-chart.pdf",
]

OUTPUT_DIR = Path("static/pages")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for pdf_path in PDF_FILES:
        if not os.path.exists(pdf_path):
            print(f"SKIP (not found): {pdf_path}")
            continue

        pdf_name = Path(pdf_path).stem  # e.g. "owner-manual"
        print(f"Converting: {pdf_path}")

        images = convert_from_path(pdf_path, dpi=150, poppler_path=POPPLER_PATH)

        for i, img in enumerate(images):
            page_num = i + 1
            filename = f"{pdf_name}_p{page_num}.png"
            filepath = OUTPUT_DIR / filename
            img.save(filepath, "PNG", optimize=True)
            print(f"  -> {filename}")

        print(f"  {len(images)} pages saved")

    print(f"\nDone. All PNGs in {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()