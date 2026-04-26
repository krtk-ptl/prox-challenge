# Vulcan OmniPro 220 - AI Welding Assistant

A domain-grounded AI assistant for the Vulcan OmniPro 220 multiprocess welder. It answers technical questions about duty cycles, polarity setup, wire speed settings, and troubleshooting, backed entirely by the machine's own manuals. Every answer is sourced from retrieved manual chunks. The agent generates four types of interactive artifacts (polarity diagrams, duty cycle calculators, troubleshooting flowcharts, settings configurators) rendered in sandboxed iframes, alongside prose explanations with page references.

The system accepts both text and image input. Upload a photo of your weld bead, settings panel, or broken part and Claude Vision analyzes it and cross-references the manual.

---

## Demo

> **Live:** https://prox-vulcan-ai.vercel.app
>
> Backend runs on Render free tier. First request after idle may take ~30 seconds.

Video walkthrough: *link will be added here*

---

## Setup

```bash
git clone https://github.com/krtk-ptl/prox-challenge.git
cd prox-challenge

cp .env.example .env
# Required: paste your ANTHROPIC_API_KEY
```

**Start backend** (Terminal 1):
```bash
pip install -r requirements.txt
python -m uvicorn api:app --port 8000
```

**Start frontend** (Terminal 2):
```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:3000** and you're good to go.

The pre-built ChromaDB index is committed to the repo (`chroma_db/`, 66 chunks). **No ingestion step is required to run the app.** The only key the running application needs is `ANTHROPIC_API_KEY`.

---

## How the Agent Works

On every user message, the backend runs three steps before streaming begins: classify the question, retrieve relevant manual context via hybrid search, and construct a specialized prompt. Claude's response is then streamed token-by-token to the frontend via SSE.

### Request Flow

```
User message (text + optional image)
        |
        v
  +-------------------------------------+
  |  1. Classify (Claude Haiku)         |  ~$0.0003, max_tokens=10
  |     > polarity | duty_cycle         |
  |     > troubleshoot | settings       |
  |     > general                       |
  +-----------------+-------------------+
                    |
                    v
  +-------------------------------------+
  |  2. Hybrid Retrieval                |  Top 5 chunks after RRF merge
  |     ChromaDB vector search          |  cosine similarity (semantic)
  |     + BM25 keyword search           |  exact term matching
  |     merged via Reciprocal Rank      |  100% local, no API cost
  |     Fusion (k=60)                   |  ~2,900 tokens per query
  +-----------------+-------------------+
                    |
                    v
  +-------------------------------------+
  |  3. Generate (Claude, streamed)     |  Type-specific system prompt
  |     Base prompt + artifact          |  + RAG context + conversation
  |     prompt per category             |  history (last 4 exchanges)
  +-----------------+-------------------+
                    | SSE stream
                    v
  +-------------------------------------+
  |  Frontend                           |
  |  - Token-by-token text display      |
  |  - Artifact extraction + iframe     |
  |  - Markdown rendering               |
  +-------------------------------------+
```

### Hybrid Search: Why Both Vector and BM25

Technical welding queries fall into two categories that a single search mode cannot handle alone:

- **Semantic queries** like "my welds are bubbly and full of holes" need vector similarity to find the porosity troubleshooting section, even though the query never uses the word "porosity."
- **Exact-term queries** like "DCEN polarity", "Dinse socket", or "duty cycle at 200A" need keyword matching because these technical terms must match verbatim. Embedding models can miss niche abbreviations.

The system runs both searches in parallel and merges results using Reciprocal Rank Fusion:

```
RRF_score(chunk) = 1/(rank_in_vector + 60) + 1/(rank_in_bm25 + 60)
```

Chunks that appear in both result lists get boosted. Chunks that only appear in one still get included. The BM25 index is built once at server startup from the ChromaDB contents (66 documents, takes <1ms). Both searches are local with zero API cost.

### Streaming Protocol

The backend uses Server-Sent Events (SSE) via FastAPI's `StreamingResponse`. Events are emitted in this sequence:

| Event | Payload | Purpose |
|-------|---------|---------|
| `metadata` | `{question_type, model}` | Tells frontend the classification result before tokens start |
| `token` | `{text}` | Each text chunk as Claude generates, drives progressive display |
| `done` | `{tokens_used}` | Stream complete, includes total token usage |

The frontend accumulates `token` events progressively. During streaming, any `<artifact>` tag content is hidden from the display so the user sees only the prose explanation. After the stream completes, the full text is parsed: prose goes into a markdown renderer, artifact code goes into a sandboxed iframe.

### Conversation State

The frontend holds the complete message history and sends the last 8 messages (4 exchanges) with every request. Artifact code in assistant history is stripped and replaced with `[interactive artifact was shown]` to save tokens. The backend is stateless: it receives a question + context and streams a response.

---

## Knowledge Extraction

### Source Material

Three PDFs from `files/`:

| PDF | Pages | Content | Extraction Method |
|-----|-------|---------|-------------------|
| `owner-manual.pdf` | 48 | Full technical reference: setup, processes, specs, troubleshooting tables | pdfplumber (text + structured tables) |
| `quick-start-guide.pdf` | 2 | Abbreviated setup with diagrams | pdfplumber (text) |
| `selection-chart.pdf` | 1 | Process selection matrix, pure image, no extractable text | Claude Vision API to structured text |

### Why pdfplumber Over pypdf

The owner's manual contains critical data in tables: duty cycle specs, amperage ranges, troubleshooting matrices, wire speed parameters. Standard pypdf (`PdfReader`) extracts these as flat text and row/column structure is destroyed. A query like "duty cycle at 200A on 240V" retrieves garbled text where "200A" and "25%" are no longer associated.

pdfplumber extracts tables as structured rows, which are converted to markdown table format during ingestion. This preserves the relationship between amperage, duty cycle percentage, weld time, and rest time. The duty cycle table chunk now looks like:

```
| Amperage | Duty Cycle | Weld Time | Rest Time |
| --- | --- | --- | --- |
| 200A | 25% | 2.5 min | 7.5 min |
| 130A | 60% | 6 min | 4 min |
| 115A | 100% | 10 min | 0 min |
```

This is directly searchable and retrievable.

### Vision Extraction for Image-Based PDFs

`selection-chart.pdf` yields 0 characters from any text extractor because it is a scanned image. The ingestion pipeline (`ingest_vision.py`) converts each page to a JPEG at 200 DPI via Poppler, sends it to Claude Vision with a structured extraction prompt, and ingests the resulting text into ChromaDB with `extraction: "vision"` metadata.

### Chunking

All text is split into word-based chunks of 500 words with 50-word overlap. Table text and non-table text from the same page are combined, with deduplication to avoid double-counting content that appears in both the table extraction and the full-text extraction. Each chunk carries metadata: `source` (PDF filename), `page` (1-indexed), and optionally `extraction: "vision"`.

### Embedding and Storage

ChromaDB uses the all-MiniLM-L6-v2 sentence transformer for embeddings, which runs 100% locally with no API cost. The index is persistent (stored in `chroma_db/`) and committed to git so reviewers skip the ingestion step entirely.

| Metric | Value |
|--------|-------|
| Total chunks | 66 (64 text + 2 vision) |
| Chunks retrieved per query | 5 (after RRF merge) |
| Avg tokens per retrieval | ~2,900 |
| Full manual tokens | ~105,000 |
| Cost reduction vs full context | ~97% |

---

## Question Classification

A single Claude Haiku call (`max_tokens=10`, ~$0.0003) classifies each question into one of 5 categories. The classifier is hardcoded to `claude-haiku-4-5` regardless of the main `CLAUDE_MODEL` setting so it stays cheap and fast.

| Category | Triggers | Artifact Generated |
|----------|----------|-------------------|
| `polarity` | Cable connections, DCEP/DCEN, which socket, torch setup | Interactive SVG polarity diagram with process selector |
| `duty_cycle` | Continuous weld time, overheating, amperage limits, rest time | Duty cycle calculator with process/voltage dropdowns |
| `troubleshoot` | Porosity, spatter, arc won't start, wire not feeding | Clickable decision-tree flowchart |
| `settings` | Voltage, wire speed, gas type, material thickness | Settings configurator with process/material/thickness inputs |
| `general` | Safety, maintenance, overview, comparisons | Text-only (artifact only if genuinely helpful) |

Each category injects a type-specific artifact prompt into the system message. This makes artifact generation reliable because Claude knows exactly what format to produce, instead of hoping a generic prompt produces the right artifact type.

---

## Artifact Rendering

Claude's response contains React code wrapped in `<artifact type="react">` tags. The frontend extracts this code and renders it in a sandboxed iframe with:

- React 18 + ReactDOM (UMD builds from unpkg CDN)
- Babel standalone for JSX transpilation
- Tailwind CSS via CDN
- `sandbox="allow-scripts"` with no `allow-same-origin`, so the iframe cannot access parent DOM, cookies, or localStorage

A function-name aliasing step ensures any component name Claude generates (e.g., `PolarityDiagram`, `DutyCycleCalculator`) gets mapped to `Component`, which is what the mount script expects. This handles the unpredictability of Claude's naming choices.

---

## Design Decisions

**RAG over full-context loading.** Sending the full 48-page manual on every query costs ~$0.30 on Sonnet. ChromaDB with local embeddings retrieves only relevant chunks at ~$0.008/query. 97% cost reduction that makes the agent economically viable.

**Hybrid search over pure vector.** Pure cosine similarity misses exact technical terms like "DCEN", "Dinse socket", and "200A" because embedding models handle niche abbreviations poorly. BM25 keyword search catches these verbatim matches. RRF merges both ranked lists so that chunks appearing in both searches get boosted, while chunks from either search alone still get included.

**Claude-based classification over keyword matching.** The initial implementation used hardcoded keyword matching (`if "cable" in question or "polarity" in question`). This was brittle: "my cables are backwards" missed, "how long can I run it?" missed. A single Haiku call handles natural language variations reliably at negligible cost.

**SSE streaming over request/response.** Claude generates long responses with artifacts (often 2000+ tokens). Without streaming, the user stares at a loading spinner for 5-8 seconds. With SSE, text appears progressively and the first token is visible within 1-2 seconds.

**Pre-committed vector index.** The ingestion pipeline runs locally once. The resulting ChromaDB directory is committed to git. Reviewers clone, install, and run. No ingestion wait, no API keys needed beyond `ANTHROPIC_API_KEY`.

**Stateless backend.** The frontend owns conversation history and sends the last 4 exchanges with each request. The backend is a pure function: receives question + history, streams response. No session store, no database beyond the read-only vector index.

---

## Tracing Hard Questions

**"What's the duty cycle for MIG welding at 200A on 240V?"**

1. Classifier: `duty_cycle`
2. Hybrid search: BM25 matches "200A" and "duty cycle" verbatim in the specs table chunk. Vector search finds semantically related duty cycle content. RRF merges both, boosting the table chunk to rank 1.
3. Duty cycle artifact prompt injected. Claude generates an interactive calculator.
4. Text response: "25% duty cycle. Weld 2.5 minutes, rest 7.5 minutes per 10-minute cycle. For continuous welding, stay at 115A or below."

**"I'm getting porosity in my welds"**

1. Classifier: `troubleshoot`
2. Hybrid search: BM25 matches "porosity" verbatim in the troubleshooting section. Vector search finds "bubbly holes in weld" type content. RRF boosts the troubleshooting table chunks.
3. Troubleshooting flowchart prompt injected. Claude generates a clickable decision tree.
4. Text response walks through causes: shielding gas, polarity, dirty workpiece, CTWD, welding speed.

**"What polarity for TIG welding?"**

1. Classifier: `polarity`
2. Hybrid search: BM25 matches "TIG" and "polarity" in setup sections. Vector search finds polarity-related content across all processes.
3. Polarity diagram prompt injected. Claude generates an SVG diagram with process selector.
4. Text response: "DCEN. Electrode cable to negative, work clamp to positive. TIG is the only process on this welder that uses DCEN."

**Image upload: photo of a weld bead**

1. Classifier runs on the auto-generated text question.
2. Hybrid search retrieves general welding tips and weld quality sections.
3. Image is sent to Claude as a multimodal message alongside RAG context.
4. Claude analyzes the weld objectively, identifies visible defects (or confirms quality), and cross-references manual troubleshooting data.

---

## Project Structure

```
prox-challenge/
├── api.py                # FastAPI backend: SSE streaming, hybrid search, classifier, prompts
├── ingest.py             # PDF text+table extraction to ChromaDB (pdfplumber)
├── ingest_vision.py      # Vision extraction for image-based PDFs to ChromaDB
├── requirements.txt      # Python dependencies
├── render.yaml           # Render deployment config
├── .env.example          # Template for ANTHROPIC_API_KEY
├── chroma_db/            # Pre-committed vector index (66 chunks)
├── files/                # Source PDFs (owner manual, quick start, selection chart)
└── frontend/             # Next.js 16 app
    ├── app/
    │   ├── page.tsx      # Chat UI: streaming reader, artifact renderer, image upload
    │   ├── layout.tsx    # App layout
    │   └── globals.css   # Tailwind styles
    ├── package.json
    └── ...
```

---

## Regenerating the Index

The pre-built index ships with the repo and the app works without this step. Only run ingestion if you modify the parsing or chunking logic.

```bash
# Text + table extraction (free, local only)
python ingest.py

# Vision extraction for image-based PDFs (~$0.02-0.05, uses Claude Vision API)
python ingest_vision.py
```

Both scripts are idempotent. `ingest.py` deletes and recreates the ChromaDB collection. `ingest_vision.py` appends vision chunks with non-colliding IDs.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, React 18, Tailwind CSS v4, react-markdown, remark-gfm |
| Backend | Python 3.12, FastAPI, Anthropic SDK, SSE streaming |
| PDF Extraction | pdfplumber (structured tables + text), Claude Vision API (image PDFs) |
| Search | Hybrid: ChromaDB vector (all-MiniLM-L6-v2) + BM25 keyword, merged via RRF |
| AI | Claude Haiku (classifier, ~$0.0003/call) + Claude main model (configurable) |
| Deployment | Vercel (frontend), Render (backend) |
