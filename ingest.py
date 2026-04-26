import os
import chromadb
import pdfplumber
from dotenv import load_dotenv

load_dotenv()

chroma = chromadb.PersistentClient(path="./chroma_db")


def extract_text_from_pdf(pdf_path):
    """Extract text + tables from PDF using pdfplumber.
    
    Key improvement over pypdf: tables are extracted as structured markdown
    instead of losing row/column alignment. This means duty cycle tables,
    specifications, and troubleshooting matrices retain their structure.
    """
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            page_parts = []

            # --- Extract tables as markdown ---
            tables = page.extract_tables()
            table_texts = []
            if tables:
                for table in tables:
                    if not table:
                        continue
                    # Build markdown table from rows
                    md_rows = []
                    for row_idx, row in enumerate(table):
                        # Clean cells: replace None with empty string, strip whitespace
                        cells = [str(cell).strip() if cell else "" for cell in row]
                        md_row = "| " + " | ".join(cells) + " |"
                        md_rows.append(md_row)
                        # Add header separator after first row
                        if row_idx == 0:
                            separator = "| " + " | ".join(["---"] * len(cells)) + " |"
                            md_rows.append(separator)
                    if md_rows:
                        table_text = "\n".join(md_rows)
                        table_texts.append(table_text)
                        page_parts.append(table_text)

            # --- Extract regular text (excluding text already in tables) ---
            # Get full page text
            full_text = page.extract_text() or ""

            # If we got tables, try to filter out table text from the full text
            # to avoid duplication. Simple approach: if tables exist, remove
            # lines that appear in table cells.
            if tables and full_text.strip():
                # Collect all cell values from tables for dedup
                table_cell_values = set()
                for table in tables:
                    if not table:
                        continue
                    for row in table:
                        if not row:
                            continue
                        for cell in row:
                            if cell and str(cell).strip():
                                # Add individual cell values (cleaned)
                                val = str(cell).strip()
                                if len(val) > 3:  # skip tiny values like "A" or "V"
                                    table_cell_values.add(val)

                # Filter: keep lines that don't heavily overlap with table cells
                filtered_lines = []
                for line in full_text.split("\n"):
                    line_stripped = line.strip()
                    if not line_stripped:
                        continue
                    # Check if this line is mostly table content
                    is_table_line = False
                    for cell_val in table_cell_values:
                        if cell_val in line_stripped or line_stripped in cell_val:
                            is_table_line = True
                            break
                    if not is_table_line:
                        filtered_lines.append(line_stripped)

                non_table_text = "\n".join(filtered_lines)
                if non_table_text.strip():
                    page_parts.insert(0, non_table_text)  # text before tables
            elif full_text.strip():
                # No tables on this page, just use full text
                page_parts.append(full_text.strip())

            # Combine everything for this page
            combined = "\n\n".join(page_parts)
            if combined.strip():
                pages.append({
                    "text": combined.strip(),
                    "page": i + 1,
                    "source": os.path.basename(pdf_path)
                })

    return pages


def chunk_text(pages, chunk_size=500, overlap=50):
    """Split pages into word-based chunks. Same logic as before."""
    chunks = []
    for page_data in pages:
        text = page_data["text"]
        words = text.split()
        for i in range(0, len(words), chunk_size - overlap):
            chunk = " ".join(words[i:i + chunk_size])
            if chunk.strip():
                chunks.append({
                    "text": chunk,
                    "page": page_data["page"],
                    "source": page_data["source"]
                })
    return chunks


def ingest_pdfs():
    pdf_files = [
        "files/owner-manual.pdf",
        "files/quick-start-guide.pdf",
        "files/selection-chart.pdf"
    ]

    # Delete existing collection and recreate for idempotent ingestion
    try:
        chroma.delete_collection(name="vulcan_manual")
        print("Cleared existing collection.")
    except Exception:
        pass

    collection = chroma.get_or_create_collection(name="vulcan_manual")

    all_chunks = []
    for pdf_path in pdf_files:
        if not os.path.exists(pdf_path):
            print(f"  SKIP (not found): {pdf_path}")
            continue
        print(f"Extracting: {pdf_path}")
        pages = extract_text_from_pdf(pdf_path)
        chunks = chunk_text(pages)
        all_chunks.extend(chunks)
        print(f"  -> {len(pages)} pages, {len(chunks)} chunks")

    if not all_chunks:
        print("No chunks extracted. Check that PDF files exist in files/ directory.")
        return

    print(f"\nTotal chunks: {len(all_chunks)}")
    print("Storing in ChromaDB with default embeddings...")

    collection.add(
        ids=[f"chunk_{i}" for i in range(len(all_chunks))],
        documents=[c["text"] for c in all_chunks],
        metadatas=[{"source": c["source"], "page": c["page"]} for c in all_chunks]
    )

    print(f"Done. {len(all_chunks)} chunks stored in ChromaDB.")


if __name__ == "__main__":
    ingest_pdfs()
