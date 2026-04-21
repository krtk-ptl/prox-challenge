import os
import chromadb
from pypdf import PdfReader
from dotenv import load_dotenv

load_dotenv()

chroma = chromadb.PersistentClient(path="./chroma_db")

def extract_text_from_pdf(pdf_path):
    reader = PdfReader(pdf_path)
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        if text and text.strip():
            pages.append({"text": text.strip(), "page": i + 1, "source": os.path.basename(pdf_path)})
    return pages

def chunk_text(pages, chunk_size=500, overlap=50):
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
