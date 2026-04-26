# Vulcan OmniPro 220 — AI Welding Assistant

A multimodal AI agent for the Vulcan OmniPro 220 multiprocess welder. Ask it anything about setup, settings, troubleshooting, or duty cycles, get accurate answers with interactive visual tools, not just text walls. Upload a photo of your weld or settings panel and get instant analysis.

Built for the [Prox Founding Engineer Challenge](https://useprox.com/join/challenge).

![Status](https://img.shields.io/badge/status-live-brightgreen) ![Claude](https://img.shields.io/badge/AI-Claude%20API-orange) ![RAG](https://img.shields.io/badge/RAG-ChromaDB-blue) ![Streaming](https://img.shields.io/badge/SSE-streaming-purple)

## Live Demo

> **https://prox-vulcan-ai.vercel.app**
>
> Backend runs on Render free tier, first load may take ~30s if the server is cold.

## Video Walkthrough

> *Link will be added here*

## Setup (under 2 minutes)

```bash
git clone https://github.com/krtk-ptl/prox-challenge.git
cd prox-challenge
cp .env.example .env
```

Add your Anthropic API key to `.env`:
```
ANTHROPIC_API_KEY=sk-ant-...
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

Open **http://localhost:3000** — that's it.

> **Note:** The ChromaDB vector index is pre-committed in the repo. You do **not** need to run `ingest.py` — the backend works immediately after install. Re-run `ingest.py` only if you want to rebuild the index from scratch.

## How It Works

```
User Question (text + optional image)
         │
         ▼
┌──────────────────────────────────────┐
│            FastAPI Backend            │
│                                      │
│  1. Classify question (Claude Haiku) │
│  2. Retrieve context (ChromaDB RAG)  │
│  3. Generate answer (Claude, streamed)│
└──────────────────┬───────────────────┘
                   │ SSE stream
                   ▼
┌──────────────────────────────────────┐
│           Next.js Frontend            │
│                                      │
│  • Markdown rendering (react-markdown)│
│  • Token-by-token streaming display   │
│  • React artifact sandbox (iframe)    │
└──────────────────────────────────────┘
```

1. **User asks a question** (text, image, or both) in the chat UI
2. **Claude Haiku classifies** the question into one of 5 categories (polarity, duty cycle, troubleshooting, settings, general) — each triggers a specialized prompt
3. **ChromaDB retrieves** the top 5 most relevant chunks from the ingested manual (~2,900 tokens vs 105,000 for the full PDF)
4. **Claude generates** a text answer with page references + a React artifact when appropriate — streamed token-by-token via SSE
5. **Frontend renders** markdown progressively as tokens arrive, then executes the React artifact in a sandboxed iframe

## Features

**Interactive Artifacts** — 4 types of generated React tools based on question category:

| Tool | Trigger Example | What It Does |
|------|----------------|--------------|
| Polarity Diagram | "What polarity for TIG?" | SVG showing cable → socket connections per process |
| Duty Cycle Calculator | "Duty cycle at 200A on 240V?" | Interactive table with process/voltage dropdowns |
| Troubleshooting Flowchart | "I'm getting porosity" | Clickable decision tree leading to fixes |
| Settings Configurator | "Settings for 1/8" mild steel MIG" | Recommends voltage, wire speed, gas, tip size |

**Multimodal Input** — Upload a photo of your weld, settings panel, or broken part. Claude Vision analyzes it and cross-references the manual.

**Conversation Memory** — The agent tracks the last 4 exchanges. Ask about MIG polarity, then follow up with "what about for TIG?" — it understands the context.

**SSE Streaming** — Responses stream token-by-token. No spinner, no waiting for the full response.

**Vision-Extracted PDFs** — The selection chart PDF (pure image, no extractable text) is processed via Claude Vision API and ingested alongside text-extracted content.

## Design Decisions

**RAG over full-context loading.** The owner's manual is 48 pages. Full-context would cost ~$0.30/query on Sonnet. ChromaDB with all-MiniLM-L6-v2 embeddings (runs 100% locally, no API cost) retrieves only relevant chunks — ~$0.008/query. 97% cost reduction.

**pdfplumber for table extraction.** Standard pypdf loses table structure — row/column data becomes garbled text. pdfplumber extracts tables as structured markdown, so duty cycle data, specs, and troubleshooting matrices retain their format in the vector store.

**Claude-based question classification.** A single Haiku call (~$0.0003) classifies each question into 5 types. Each type has a specialized system prompt that tells Claude exactly what artifact to generate. This makes artifact output reliable instead of random.

**Sandboxed iframe artifact rendering.** Claude's React code is extracted from `<artifact>` tags, wrapped in a full HTML document with React 18 + Babel + Tailwind via CDN, and rendered in a sandboxed iframe. Function-name aliasing ensures any component name Claude generates maps to the mount point.

**Pre-committed vector index.** The ChromaDB index is committed to git. Reviewers clone → install → run. No ingestion step required.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, React 18, Tailwind CSS v4, react-markdown, remark-gfm |
| Backend | Python 3.12, FastAPI, Anthropic SDK, SSE streaming |
| PDF Extraction | pdfplumber (tables + text), Claude Vision API (image-based PDFs) |
| RAG | ChromaDB (persistent vector store), all-MiniLM-L6-v2 embeddings (local) |
| AI Model | Claude Haiku (classifier) + Claude configurable via `CLAUDE_MODEL` env var |
| Deployment | Vercel (frontend), Render (backend) |

## Project Structure

```
prox-challenge/
├── api.py                # FastAPI backend: SSE streaming, classifier, RAG, prompts
├── ingest.py             # PDF text+table extraction → ChromaDB (pdfplumber)
├── ingest_vision.py      # Vision extraction for image-based PDFs → ChromaDB
├── requirements.txt      # Python dependencies
├── render.yaml           # Render deployment config
├── .env.example          # Template for API key
├── chroma_db/            # Pre-committed vector index (66 chunks)
├── files/                # Source PDFs (owner manual, quick start, selection chart)
└── frontend/             # Next.js app
    ├── app/
    │   ├── page.tsx      # Chat UI, streaming reader, artifact renderer
    │   ├── layout.tsx    # App layout
    │   └── globals.css   # Tailwind styles
    ├── package.json
    └── ...
```
