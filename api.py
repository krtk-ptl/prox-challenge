import os
import re
import json
import chromadb
from anthropic import Anthropic
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from typing import Optional
from rank_bm25 import BM25Okapi

load_dotenv()

app = FastAPI()

# Allow localhost for dev + any deployed frontend URL via env var
allowed_origins = ["http://localhost:3000"]
extra_origin = os.getenv("FRONTEND_URL")
if extra_origin:
    allowed_origins.append(extra_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.staticfiles import StaticFiles

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# Model from env — use haiku for dev, sonnet for production
MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5")
# Classifier always uses Haiku regardless of MODEL — cheap, fast, no need for Sonnet
CLASSIFIER_MODEL = "claude-haiku-4-5"

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
chroma = chromadb.PersistentClient(path="./chroma_db")
from embeddings import bge_embed_fn
collection = chroma.get_or_create_collection(name="vulcan_manual", embedding_function=bge_embed_fn)


# --- BM25 index (built once at startup from ChromaDB contents) ---

def build_bm25_index():
    """Load all chunks from ChromaDB and build a BM25 index for keyword search.
    Runs once at server startup. Cost: $0 (pure local computation).
    """
    all_data = collection.get(include=["documents", "metadatas"])
    documents = all_data["documents"]
    metadatas = all_data["metadatas"]
    ids = all_data["ids"]

    # Tokenize: simple lowercase word split. Good enough for technical terms
    # like "DCEN", "200A", "porosity" which need exact matching.
    tokenized = [doc.lower().split() for doc in documents]

    bm25 = BM25Okapi(tokenized)

    print(f"BM25 index built: {len(documents)} documents")
    return bm25, documents, metadatas, ids


bm25_index, bm25_documents, bm25_metadatas, bm25_ids = build_bm25_index()


def hybrid_search(query: str, n_results: int = 5) -> list[dict]:
    """Run both ChromaDB vector search and BM25 keyword search, merge with RRF.

    Reciprocal Rank Fusion: score = sum(1 / (rank + k)) across both result lists.
    k=60 is standard — prevents top-ranked results from dominating too heavily.

    Why hybrid:
    - Vector search handles semantic queries: "my welds are bubbly" → finds porosity content
    - BM25 handles exact terms: "DCEN", "Dinse socket", "200A duty cycle" → verbatim match
    - Neither alone covers both. RRF promotes chunks that appear in both lists.

    Cost: $0 — both searches are local.
    """
    k = 60  # RRF constant

    # --- Vector search via ChromaDB ---
    vector_results = collection.query(
        query_texts=[query],
        n_results=min(n_results * 2, len(bm25_documents))  # fetch more candidates for better merging
    )
    vector_ids = vector_results["ids"][0]

    # --- BM25 keyword search ---
    tokenized_query = query.lower().split()
    bm25_scores = bm25_index.get_scores(tokenized_query)

    # Get top candidates from BM25 (same count as vector)
    n_candidates = min(n_results * 2, len(bm25_documents))
    # argsort descending, take top n
    import numpy as np
    top_bm25_indices = np.argsort(bm25_scores)[::-1][:n_candidates]
    bm25_ranked_ids = [bm25_ids[i] for i in top_bm25_indices if bm25_scores[i] > 0]

    # --- RRF merge ---
    rrf_scores = {}

    # Score from vector search
    for rank, doc_id in enumerate(vector_ids):
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + 1.0 / (rank + k)

    # Score from BM25 search
    for rank, doc_id in enumerate(bm25_ranked_ids):
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + 1.0 / (rank + k)

    # Sort by RRF score descending, take top n_results
    sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)[:n_results]

    # --- Filter out weak chunks: drop anything below 50% of the top RRF score ---
    if sorted_ids:
        top_score = rrf_scores[sorted_ids[0]]
        threshold = top_score * 0.50
        sorted_ids = [doc_id for doc_id in sorted_ids if rrf_scores[doc_id] >= threshold]

    # --- Fetch full chunk data for the winning IDs ---
    # Build a lookup from our stored data
    id_to_idx = {doc_id: idx for idx, doc_id in enumerate(bm25_ids)}

    results = []
    for doc_id in sorted_ids:
        idx = id_to_idx.get(doc_id)
        if idx is not None:
            results.append({
                "id": doc_id,
                "text": bm25_documents[idx],
                "metadata": bm25_metadatas[idx],
                "rrf_score": rrf_scores[doc_id],
            })
            
    print(f"Query: {query}")
    for r in results:
        print(f"  RRF={r['rrf_score']:.4f} | {r['metadata']['source']} p{r['metadata']['page']} | {r['text'][:80]}...")

    return results


# --- Request models ---

class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str

class QueryRequest(BaseModel):
    question: str
    history: Optional[list[ChatMessage]] = None  # conversation history
    image: Optional[str] = None  # base64 encoded image (JPEG/PNG)
    image_type: Optional[str] = None  # "image/jpeg", "image/png", etc.


# --- Question classifier (Claude-based) ---

CLASSIFIER_PROMPT = """You are a question classifier for a welding assistant chatbot about the Vulcan OmniPro 220 welder.

Classify the user's question into EXACTLY ONE of these 5 categories:

- polarity: questions about cable connections, which socket to use, electrode vs work clamp, DCEP/DCEN, which terminal is positive/negative, how to connect cables for MIG/TIG/Stick/Flux-Core
- duty_cycle: questions about how long you can weld continuously, duty cycle percentages, overheating, rest time, weld time, amperage limits over time
- troubleshoot: questions about welding defects (porosity, spatter, cracking, undercut), equipment problems (wire not feeding, arc won't start, welder won't turn on, no gas flow), bad weld quality
- settings: questions about recommended voltage, wire speed, amperage, gas type, material thickness, welding parameters for a specific job
- general: everything else — safety, machine overview, maintenance, comparisons, how welding works, setup questions that don't fit above

Respond with ONLY the category name, nothing else. No explanation, no punctuation. Just one of: polarity, duty_cycle, troubleshoot, settings, general"""

def classify_question(question: str) -> str:
    """Classify question using Claude Haiku. ~$0.0003 per call. Always uses latest Haiku regardless of MODEL env var."""
    try:
        response = client.messages.create(
            model=CLASSIFIER_MODEL,
            max_tokens=10,  # category name is at most 12 chars
            system=CLASSIFIER_PROMPT,
            messages=[{"role": "user", "content": question}]
        )
        category = response.content[0].text.strip().lower()
        # Validate — if Claude returns something unexpected, fall back to general
        valid = {"polarity", "duty_cycle", "troubleshoot", "settings", "general"}
        return category if category in valid else "general"
    except Exception as e:
        print(f"Classifier error: {e} — falling back to general")
        return "general"


# --- Artifact prompts (per question type) ---

ARTIFACT_PROMPTS = {
    "polarity": """
MANDATORY: You MUST generate a React artifact EVERY TIME this question type is asked, regardless of conversation history or prior responses. Never skip the artifact for polarity questions.

Generate a React artifact showing a visual polarity diagram.
The diagram should show the welder unit with two sockets (+ and -) and cables connecting to the correct terminals.
Show all 4 processes: MIG, Flux-Core, TIG, Stick with their correct polarity.
Include a process selector (tabs or dropdown) that updates the diagram.

Format your artifact EXACTLY like this:
<artifact type="react">
function PolarityDiagram() {
  const [process, setProcess] = React.useState('MIG');
  // your component code
  return (...);
}
</artifact>
""",
    "duty_cycle": """
MANDATORY: You MUST generate a React artifact EVERY TIME this question type is asked, regardless of conversation history or prior responses. Never skip the artifact for duty cycle questions.

Generate a React artifact with an interactive duty cycle calculator.
Include dropdowns for: Process (MIG/TIG/Stick/Flux), Voltage (120V/240V).
Show a table with amperage, duty cycle %, weld time, and rest time per 10-min cycle.
Use data exactly from the manual context provided — do NOT invent numbers.
For duty cycle percentages, use opacity or shade variations of orange (#f97316) to indicate severity — lighter orange for 100%, darker/deeper for 25-40%. Do NOT use green, red, yellow, or blue.

Format your artifact EXACTLY like this:
<artifact type="react">
function DutyCycleCalculator() {
  const [process, setProcess] = React.useState('MIG');
  const [voltage, setVoltage] = React.useState('240V');
  // your component code
  return (...);
}
</artifact>
""",
    "troubleshoot": """
RULE 1 — NON-NEGOTIABLE: Generate a React troubleshooting flowchart artifact in EVERY response to this question type. No exceptions. The artifact must appear even if you also ask a clarifying question. Generate the artifact first, then ask questions in the text if needed.

The artifact is an interactive flowchart starting with the symptom the user described, branching through Yes/No questions to specific fixes from the manual (Pages 37-40). Every branch must end at a concrete fix or "Contact Vulcan support at 1-800-444-3353". No dead ends.

TEXT RESPONSE RULE — NON-NEGOTIABLE:
The text response and the artifact must NOT duplicate informative information which is meant for user to see.

- The artifact handles all detailed logic, interaction, decision-making, and visuals.
- The text must be minimal (4-5 short sentences max).
- The text should ONLY:
  1. Briefly acknowledge or restate the user’s problem, present symptoms and
  2. Direct the user to use the interactive artifact below.

STRICTLY AVOID in text:
- Lists, decision trees, or explanations already present in the artifact
- Repeating options, processes, or data shown in the artifact

If the artifact already contains the answer, the text should not re-explain it because it add unnecessary bulk to answer..


Do NOT ask for material thickness — defect causes do not depend on thickness.

Format:
<artifact type="react">
function TroubleshootingFlow() {
  const [step, setStep] = React.useState(0);
  const [history, setHistory] = React.useState([]);
  // your component code
  return (...);
}
</artifact>
""",
    "settings": """
Do NOT generate a React artifact for settings questions. The OmniPro 220 has a built-in LCD auto-recommendation system that is more accurate than any chart we can show.

Instead, give a clear text answer that:
1. Answers the specific question with whatever guidance the manual context provides.
2. Directs the user to the welder's built-in LCD system (Page 20): press Home, select process, use Left Knob for wire diameter and Right Knob for material thickness — the machine shows its own recommended settings.
3. Includes any relevant duty cycle limits or safety notes for the process/amperage mentioned.

Generate an artifact if the user explicitly asks for a visual chart or calculator.
""",
    "general": """
Answer the question clearly and practically using the manual context.
Only generate an artifact if it would genuinely help — like a diagram or visual aid.
If you do generate one, use this format:
<artifact type="react">
function Component() {
  return (...);
}
</artifact>
"""
}


# --- System prompt with ambiguity handling ---

BASE_SYSTEM = """You are an expert assistant for the Vulcan OmniPro 220 multiprocess welder.
The user is in their garage, just bought this welder, needs clear practical help.
Be direct and practical. Reference specific page numbers from the manual when possible.
Always answer the text question FIRST with a clear explanation, then show the artifact below.
Use markdown formatting: **bold** for emphasis, bullet lists for steps.
Do NOT use em dashes (—) in your responses. Use commas, periods, colons, or parentheses instead. Write in short, clear sentences.

SETTINGS ACCURACY NOTE:
When giving specific voltage/wire speed numbers, always tell the user to cross-check using the welder's built-in LCD system: press Home, select process, then use the Left Knob (wire diameter) and Right Knob (material thickness) to get the machine's own recommendation. This is more reliable than any chart because it accounts for the exact wire and material combination. (Page 20)
- MIG (solid core, gas shielded): DCEP. Ground clamp to NEGATIVE (-) socket. Wire feed cable to POSITIVE (+) socket. (Page 14)
- Flux-Core (gasless, self-shielded): DCEN. Ground clamp to POSITIVE (+) socket. Wire feed cable to NEGATIVE (-) socket. (Page 13)
- TIG: DCEN. TIG torch to NEGATIVE (-) terminal. Ground clamp to POSITIVE (+) terminal. Gas: 100% Argon, 10-25 SCFH. (Page 30)
- Stick: DCEP for most electrodes. Check electrode manufacturer specs for exceptions.
These are verified from the official manual. If retrieved context contradicts these, trust these facts.

ARTIFACT STYLING (MANDATORY — follow these rules for ALL React artifacts):
The UI uses a dark theme with orange accents. Your artifact renders inside an iframe with dark background (#141414).
- Background: use #141414, #1a1a1a, #262626 for surfaces. NEVER use white, #f9fafb, or light backgrounds.
- Text: use #e5e5e5 for body text, #fdba74 for headings/labels, #a3a3a3 for secondary text.
- Accent color: #f97316 (orange). Use for active tabs, selected states, primary buttons, highlights.
- Borders: use #404040 or #333333. Never use light gray borders.
- Buttons: dark background (#262626) with #404040 border. Active/selected buttons get #f97316 background with white text.
- Tables: dark header (#292929), #fdba74 header text, #262626 alternating rows, #404040 borders.
- DO NOT use blue, green, red, yellow, or any bright multi-colored elements. Use only orange (#f97316), its shades (#fdba74, #ea580c), and neutral grays.
- For status indicators (like duty cycle %), use opacity variations of orange instead of traffic-light colors.
- Font: inherit from parent (Geist). Do not set font-family in your artifact code.

ARTIFACT CODE EFFICIENCY (CRITICAL — your code WILL be truncated if too long):
- Define a shared styles object at the top and reference it. NEVER repeat inline style objects across buttons/elements.
- Use helper functions for repeated UI patterns (e.g., one function that renders a button given label, isActive).
- Keep data objects minimal — only include data directly relevant to the user's question, not every possible combination.
- Maximum artifact length: ~180 lines of code. Budget carefully — leave room for closing tags.
- Prefer arrays + .map() over copy-pasted JSX blocks.
- CRITICAL: Every artifact MUST be syntactically complete. Never end mid-expression or mid-tag. If running long, simplify the data or remove a feature — do NOT truncate. A broken artifact is worse than a simple one.

AMBIGUITY HANDLING:
If the user's question is vague or could apply to multiple welding processes (MIG, Flux-Core, TIG, Stick), ASK a clarifying question before answering. Examples:
- "How do I set it up?" → Ask which welding process they plan to use
- "What settings should I use?" → You MUST ask for ALL THREE: (1) welding process, (2) material type, (3) material thickness. Do not answer until you have all three.
- "It's not working" → Ask what specific symptom they're seeing
Do NOT guess when the answer depends on which process, voltage, or material. Ask first.
When asking for clarification on settings, always explicitly ask about thickness — it is required to give accurate recommendations.
However, if the conversation history already contains the answer (e.g., they mentioned MIG earlier), use that context and don't ask again.
EXCEPTION — TROUBLESHOOTING: For troubleshooting questions about defects (porosity, spatter, cracks, undercut, etc.), do NOT ask for material thickness. Defect causes are the same regardless of thickness. Only ask for welding process if genuinely needed and not already mentioned. Go straight to diagnosing the symptom.

CONVERSATION CONTEXT:
You have access to the recent conversation history. Use it to:
- Understand follow-up questions ("what about for TIG?" after discussing MIG polarity)
- Avoid asking for info the user already provided
- Maintain coherent multi-turn conversations

IMAGE INPUT:
When the user uploads an image, analyze it carefully and HONESTLY. Do not default to praise or criticism — assess objectively based on what you actually see.
- Describe what you observe in the image first
- If it shows a weld: assess quality honestly — list ONLY defects you can actually see, or confirm it's good if it genuinely is. Never invent problems.
- If it shows the welder, settings panel, setup, or assembly: read what's visible and advise accordingly
- If it shows damaged/broken parts: identify the issue and suggest a fix referencing the manual
- If you're unsure what the image shows, ask the user to clarify
Always cross-reference what you see with the manual context provided."""


# --- Build message history for Claude ---

def build_messages(question: str, context: str, history: list[ChatMessage] | None, image: str | None = None, image_type: str | None = None) -> list[dict]:
    """Build the messages array with conversation history + current question with RAG context."""
    messages = []

    if history:
        # Take last 8 messages (4 user + 4 assistant turns)
        recent = history[-8:]
        for msg in recent:
            # Strip artifact tags from assistant history — Claude doesn't need old React code
            content = msg.content
            if msg.role == "assistant":
                content = re.sub(r'<artifact type="react">[\s\S]*?</artifact>', '[interactive artifact was shown]', content)
            messages.append({"role": msg.role, "content": content})

    # Current question — with image if provided
    user_content = []

    # Add image first if present
    if image and image_type:
        user_content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": image_type,
                "data": image,
            },
        })

    # Add text (RAG context + question)
    text_part = f"Context from manual:\n{context}\n\nQuestion: {question}"
    if image:
        text_part += "\n\n(An image has been attached above — analyze it as part of your answer.)"

    user_content.append({
        "type": "text",
        "text": text_part,
    })

    messages.append({"role": "user", "content": user_content})

    return messages


# --- SSE streaming generator ---

async def stream_response(request: QueryRequest):
    """Generator that yields SSE events with Claude's streaming tokens.
    
    Emits status events at each pipeline stage for frontend tool-use indicators:
    1. classify → classifying the question
    2. retrieve → searching the knowledge base
    3. generate → streaming Claude's response
    """
    # Step 1: Emit classifying status, then classify
    status_event = json.dumps({"type": "status", "step": "classify", "state": "running"})
    yield f"data: {status_event}\n\n"

    question_type = classify_question(request.question)

    status_event = json.dumps({"type": "status", "step": "classify", "state": "done", "result": question_type})
    yield f"data: {status_event}\n\n"

    # Step 2: Emit retrieving status, then retrieve
    status_event = json.dumps({"type": "status", "step": "retrieve", "state": "running"})
    yield f"data: {status_event}\n\n"

    # Vary retrieval depth by question type — simple topics need fewer chunks,
    # troubleshooting/settings need more context to be thorough
    retrieval_depth = {"polarity": 4, "duty_cycle": 5, "troubleshoot": 7, "settings": 6, "general": 5}
    n_results = retrieval_depth.get(question_type, 5)

    search_results = hybrid_search(request.question, n_results=n_results)

    # Collect unique sources for the status event
    sources_seen = set()
    for r in search_results:
        src = r["metadata"].get("source", "unknown")
        sources_seen.add(src)

    status_event = json.dumps({
        "type": "status",
        "step": "retrieve",
        "state": "done",
        "chunks": len(search_results),
        "sources": list(sources_seen),
    })
    yield f"data: {status_event}\n\n"

    context = ""
    for result in search_results:
        source = result["metadata"].get("source", "unknown")
        page = result["metadata"].get("page", "?")
        context += f"[{source}, Page {page}]\n{result['text']}\n\n"

    system_prompt = BASE_SYSTEM + "\n\n" + ARTIFACT_PROMPTS[question_type]

    messages = build_messages(
        question=request.question,
        context=context,
        history=request.history,
        image=request.image,
        image_type=request.image_type,
    )

    # Step 3: Emit generating status + metadata, then stream
    status_event = json.dumps({"type": "status", "step": "generate", "state": "running"})
    yield f"data: {status_event}\n\n"

    meta_event = json.dumps({
        "type": "metadata",
        "question_type": question_type,
        "model": MODEL,
    })
    yield f"data: {meta_event}\n\n"

    # Step 4: Stream Claude's response token by token
    total_input_tokens = 0
    total_output_tokens = 0

    with client.messages.stream(
        model=MODEL,
        max_tokens=8192,
        system=system_prompt,
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            token_event = json.dumps({
                "type": "token",
                "text": text,
            })
            yield f"data: {token_event}\n\n"

        # After stream ends, get final usage stats
        final_message = stream.get_final_message()
        total_input_tokens = final_message.usage.input_tokens
        total_output_tokens = final_message.usage.output_tokens

    # Step 5: Mark generate as done + send done event with token usage
    status_event = json.dumps({"type": "status", "step": "generate", "state": "done"})
    yield f"data: {status_event}\n\n"

    done_event = json.dumps({
        "type": "done",
        "tokens_used": total_input_tokens + total_output_tokens,
    })
    yield f"data: {done_event}\n\n"


# --- Main query endpoint (now streaming) ---

@app.post("/query")
async def query(request: QueryRequest):
    return StreamingResponse(
        stream_response(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable nginx buffering if deployed behind nginx
        },
    )


@app.get("/health")
async def health():
    count = collection.count()
    return {
        "status": "ok",
        "model": MODEL,
        "chunks_indexed": count,
        "search": "hybrid (vector + BM25 + RRF)",
    }
