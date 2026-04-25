"""
ingest_vision.py — Extract text from image-based PDFs using Claude Vision API.
Targets selection-chart.pdf which pypdf can't extract (0 chars).
Sends page images to Claude Vision, gets structured text, ingests into ChromaDB.

Usage: python ingest_vision.py
Cost: ~$0.02-0.05 with Haiku (one image, one API call)

Requires: pip install pdf2image
Also requires Poppler: https://github.com/oschwartz10612/poppler-windows/releases
  - Download, extract, add bin/ folder to PATH
  - Or pass poppler_path to convert_from_path()
"""

import os
import base64
import chromadb
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

# --- Config ---
VISION_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5")
CHROMA_PATH = "./chroma_db"
COLLECTION_NAME = "vulcan_manual"

# PDFs to process with vision (add more image-based PDFs here if needed)
VISION_PDFS = [
    "files/selection-chart.pdf",
]

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
chroma = chromadb.PersistentClient(path=CHROMA_PATH)
collection = chroma.get_or_create_collection(name=COLLECTION_NAME)


def pdf_page_to_base64(pdf_path: str, page_num: int = 0) -> str:
    """Convert a PDF page to base64 JPEG using pdf2image (Poppler)."""
    try:
        from pdf2image import convert_from_path
        # 200 DPI is enough for text extraction, keeps token cost down
        images = convert_from_path(pdf_path, dpi=200, first_page=page_num + 1, last_page=page_num + 1, poppler_path=r"K:\Poppler\poppler-25.12.0\Library\bin")
        if not images:
            raise ValueError(f"No images extracted from page {page_num}")

        import io
        buffer = io.BytesIO()
        images[0].save(buffer, format="JPEG", quality=85)
        return base64.standard_b64encode(buffer.getvalue()).decode("utf-8")

    except ImportError:
        print("\n--- pdf2image not installed ---")
        print("Run: pip install pdf2image")
        print("Also install Poppler:")
        print("  Windows: https://github.com/oschwartz10612/poppler-windows/releases")
        print("  Then add the bin/ folder to your PATH")
        print("  Mac: brew install poppler")
        print("  Linux: sudo apt install poppler-utils")
        raise SystemExit(1)


def extract_text_with_vision(image_base64: str, source_name: str, page_num: int) -> str:
    """Send page image to Claude Vision API and extract all text/table content."""

    prompt = """Extract ALL text, numbers, tables, and data from this image.
This is a page from the Vulcan OmniPro 220 welder manual — likely a welding process selection chart or reference table.

Rules:
- Extract EVERY piece of text visible in the image
- For tables: preserve the row/column structure using markdown table format
- For charts/matrices: capture all axis labels, values, and cell contents
- Include headers, footnotes, labels, and any fine print
- If there are diagrams with labels, describe what they show and capture all label text
- Output plain text, no commentary — just the extracted content

Start with the page title/header, then work through the content top to bottom."""

    response = client.messages.create(
        model=VISION_MODEL,
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_base64,
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }
        ],
    )

    extracted = response.content[0].text
    tokens_in = response.usage.input_tokens
    tokens_out = response.usage.output_tokens
    print(f"  Vision API: {tokens_in} input + {tokens_out} output tokens")
    return extracted


def chunk_text(text: str, source: str, page: int, chunk_size: int = 500, overlap: int = 50) -> list[dict]:
    """Split extracted text into chunks for ChromaDB."""
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i:i + chunk_size])
        if chunk.strip():
            chunks.append({
                "text": chunk,
                "page": page,
                "source": source,
            })
    return chunks


def ingest_vision_pdfs():
    """Main: process each image-based PDF with Claude Vision and add to ChromaDB."""

    # Get existing chunk count to generate unique IDs
    existing_count = collection.count()
    print(f"Existing chunks in ChromaDB: {existing_count}")

    all_chunks = []

    for pdf_path in VISION_PDFS:
        if not os.path.exists(pdf_path):
            print(f"  SKIP (not found): {pdf_path}")
            continue

        source_name = os.path.basename(pdf_path)
        print(f"\nProcessing: {pdf_path}")

        # Get page count
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        num_pages = len(reader.pages)
        print(f"  Pages: {num_pages}")

        for page_num in range(num_pages):
            print(f"  Extracting page {page_num + 1}/{num_pages} with Vision API...")

            # Convert page to image
            image_b64 = pdf_page_to_base64(pdf_path, page_num)

            # Send to Claude Vision
            extracted_text = extract_text_with_vision(image_b64, source_name, page_num + 1)

            if not extracted_text.strip():
                print(f"    WARNING: No text extracted from page {page_num + 1}")
                continue

            print(f"    Extracted {len(extracted_text)} chars")

            # Chunk the extracted text
            chunks = chunk_text(extracted_text, source_name, page_num + 1)
            all_chunks.extend(chunks)
            print(f"    -> {len(chunks)} chunks")

    if not all_chunks:
        print("\nNo chunks extracted. Check PDF paths and Poppler installation.")
        return

    # Add to ChromaDB with IDs that don't collide with existing chunks
    start_id = existing_count
    print(f"\nAdding {len(all_chunks)} vision-extracted chunks to ChromaDB...")

    collection.add(
        ids=[f"vision_chunk_{start_id + i}" for i in range(len(all_chunks))],
        documents=[c["text"] for c in all_chunks],
        metadatas=[{"source": c["source"], "page": c["page"], "extraction": "vision"} for c in all_chunks],
    )

    print(f"Done. Total chunks in ChromaDB: {collection.count()}")
    print(f"  (was {existing_count}, added {len(all_chunks)} from vision extraction)")


if __name__ == "__main__":
    ingest_vision_pdfs()
