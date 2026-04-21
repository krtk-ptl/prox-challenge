# Vulcan OmniPro 220 — AI Welding Assistant

A multimodal AI agent for the Vulcan OmniPro 220 multiprocess welder. Ask it anything about setup, settings, troubleshooting, or duty cycles — get accurate answers with interactive visual tools, not just text walls.

Built for the [Prox Founding Engineer Challenge](https://useprox.com/join/challenge).

![Demo](https://img.shields.io/badge/status-functional-green) ![Claude](https://img.shields.io/badge/AI-Claude%20API-orange) ![RAG](https://img.shields.io/badge/RAG-ChromaDB-blue)

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
python ingest.py
python -m uvicorn api:app --port 8000
```

**Start frontend** (Terminal 2):
```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:3000** — that's it.

## How It Works

```
                        ┌──────────────────┐
                        │   User Question   │
                        └────────┬─────────┘
                                 │
                                 ▼
┌──────────────┐       ┌──────────────────┐
│   Next.js    │◄─────►│    FastAPI API    │
│   Chat UI    │       └────────┬─────────┘
└──────────────┘                │
                     ┌──────────┼──────────┐
                     ▼          ▼          ▼
              ┌───────────┐ ┌───────┐ ┌────────┐
              │  Question  │ │ChromaDB│ │ Claude │
              │ Classifier │ │  RAG   │ │  API   │
              └───────────┘ └───────┘ └────────┘
```

1. **User asks a question** in the chat UI
2. **Question classifier** routes it to one of 5 categories: polarity, duty cycle, troubleshooting, settings, or general — each with a specialized prompt
3. **ChromaDB retrieves** the top 5 most relevant chunks from the ingested manual (~2,900 tokens per query vs 105,000 for the full PDF)
4. **Claude generates** both a text answer (with page references) and a React artifact when the question warrants an interactive tool
5. **Frontend renders** markdown in the chat bubble and executes the React artifact in a sandboxed iframe with Babel + Tailwind

## Interactive Tools

The agent generates 4 types of interactive artifacts based on question type:

**Polarity Diagram** — Ask "What polarity for TIG?" and get an SVG diagram showing which cable plugs into which socket (positive/negative) for each welding process. Includes a process selector to compare MIG, Flux, TIG, and Stick setups.

**Duty Cycle Calculator** — Ask "What's the duty cycle at 200A on 240V?" and get an interactive table with process and voltage dropdowns. Shows amperage ranges, duty cycle percentages, weld time and rest time per 10-minute cycle. Color-coded: green (100%), yellow (60%), red (25-40%).

**Troubleshooting Flowchart** — Ask "I'm getting porosity in my welds" and get a clickable decision tree. Starts with your symptom, branches through Yes/No diagnostic steps, leads to specific fixes — all sourced from the manual's troubleshooting section.

**Settings Configurator** — Ask "Settings for 1/8 inch mild steel MIG" and get a tool with dropdowns for process, material, and thickness. Outputs recommended voltage, wire speed, amperage, gas type, and tip size based on the manual's parameter charts.

## Design Decisions

**RAG instead of full-context loading.** The owner's manual is 48 pages. Sending it all on every query would burn ~$0.30/query on Sonnet. ChromaDB with sentence-transformer embeddings (all-MiniLM-L6-v2, runs 100% locally — no API cost) retrieves only relevant chunks, dropping per-query cost to ~$0.008. That's a 97% reduction that makes the agent economically viable for real usage.

**Question classification with type-specific prompts.** A single generic prompt produces inconsistent artifacts — sometimes Claude generates a diagram, sometimes it doesn't. By classifying questions into 5 types via keyword matching, each type gets a specialized system prompt that tells Claude exactly what kind of artifact to produce and in what format. This makes artifact generation reliable rather than random.

**Sandboxed iframe artifact rendering.** Claude's response contains React code wrapped in `<artifact>` tags. The frontend extracts this code, wraps it in a full HTML document with React 18 + Babel + Tailwind loaded from CDN, and renders it in a sandboxed iframe. This mirrors how Claude.ai renders artifacts — safe execution isolation with full React capability. A function-name aliasing step ensures any component name Claude picks gets mapped to the mount point.

**Markdown in chat bubbles.** Text responses use react-markdown with remark-gfm so that bold text, lists, tables, and code blocks all render properly instead of showing raw markdown syntax.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, React 18, Tailwind CSS v4, react-markdown |
| Backend | Python 3.12, FastAPI, Anthropic SDK |
| RAG | ChromaDB (local persistent vector store), all-MiniLM-L6-v2 embeddings |
| AI Model | Claude (configurable via `CLAUDE_MODEL` env var) |

## Known Limitations

- **`selection-chart.pdf` not ingested** — it's a scanned image, so pypdf extracts 0 text. Needs Claude Vision or OCR to extract the welding process selection matrix.
- **No conversation memory** — each query is independent. The agent doesn't remember prior context.
- **No streaming** — responses arrive all at once after Claude finishes. SSE streaming would improve perceived responsiveness.
- **No ambiguity handling** — vague questions like "how do I set it up?" get generic answers instead of clarifying follow-ups.

## Project Structure

```
prox-challenge/
├── api.py              # FastAPI backend — query endpoint, classifier, prompts
├── ingest.py           # PDF chunking + ChromaDB ingestion (run once)
├── query.py            # Standalone RAG test script
├── requirements.txt    # Python dependencies
├── .env.example        # Template for API key
├── files/              # Source PDFs (owner manual, quick start, selection chart)
└── frontend/           # Next.js app
    ├── app/
    │   ├── page.tsx    # Chat UI + artifact renderer
    │   ├── layout.tsx  # App layout
    │   └── globals.css # Tailwind styles
    ├── package.json
    └── ...
```
