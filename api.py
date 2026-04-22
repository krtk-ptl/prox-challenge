import os
import re
import chromadb
from anthropic import Anthropic
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from typing import Optional

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

# Model from env — use haiku for dev, sonnet for production
MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5")

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
chroma = chromadb.PersistentClient(path="./chroma_db")
collection = chroma.get_or_create_collection(name="vulcan_manual")


# --- Request models ---

class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str

class QueryRequest(BaseModel):
    question: str
    history: Optional[list[ChatMessage]] = None  # conversation history


# --- Question classifier ---

def classify_question(question: str) -> str:
    q = question.lower()
    if any(w in q for w in ["polarity", "cable", "socket", "ground clamp", "electrode", "connect", "plug", "tig setup", "stick setup", "mig setup", "wire feed power"]):
        return "polarity"
    if any(w in q for w in ["duty cycle", "how long", "overheat", "rest", "continuous", "amperage limit"]):
        return "duty_cycle"
    if any(w in q for w in ["porosity", "spatter", "crack", "defect", "troubleshoot", "problem", "issue", "wrong", "bad weld", "not working", "wire feed", "arc won't", "no arc", "won't start"]):
        return "troubleshoot"
    if any(w in q for w in ["settings", "voltage", "wire speed", "thickness", "material", "steel", "aluminum", "stainless", "configure", "recommend", "what should i set"]):
        return "settings"
    return "general"


# --- Artifact prompts (per question type) ---

ARTIFACT_PROMPTS = {
    "polarity": """
You MUST generate a React artifact showing a visual polarity diagram.
The diagram should show the welder unit with two sockets (+ and -) and cables connecting to the correct terminals.
Use colored SVG elements inside React: red for positive, black/blue for negative.
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
You MUST generate a React artifact with an interactive duty cycle calculator.
Include dropdowns for: Process (MIG/TIG/Stick/Flux), Voltage (120V/240V).
Show a table with amperage, duty cycle %, weld time, and rest time per 10-min cycle.
Use data exactly from the manual context provided — do NOT invent numbers.
Color code: green for 100%, yellow for 60%, orange/red for 25-40%.

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
You MUST generate a React artifact with an interactive troubleshooting flowchart.
Start with the reported symptom, then show Yes/No decision nodes leading to specific fixes.
Use the manual's troubleshooting section data.
Style as a step-by-step clickable flow, not a static list.
IMPORTANT: Every path in the flowchart must lead to a concrete resolution or a "Contact Vulcan support" fallback. No dead ends.

Format your artifact EXACTLY like this:
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
You MUST generate a React artifact — a settings configurator.
Inputs: Welding Process, Material Type, Material Thickness (gauge or mm).
Output: Recommended Voltage, Wire Speed, Amperage, Gas type, Tip size.
Use actual values from the manual's welding parameter charts.

Format your artifact EXACTLY like this:
<artifact type="react">
function SettingsConfigurator() {
  const [process, setProcess] = React.useState('MIG');
  const [material, setMaterial] = React.useState('mild_steel');
  const [thickness, setThickness] = React.useState('1/8');
  // your component code
  return (...);
}
</artifact>
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

AMBIGUITY HANDLING:
If the user's question is vague or could apply to multiple welding processes (MIG, Flux-Core, TIG, Stick), ASK a clarifying question before answering. Examples:
- "How do I set it up?" → Ask which welding process they plan to use
- "What settings should I use?" → Ask what material, thickness, and process
- "It's not working" → Ask what specific symptom they're seeing
Do NOT guess when the answer depends on which process, voltage, or material. Ask first.
However, if the conversation history already contains the answer (e.g., they mentioned MIG earlier), use that context and don't ask again.

CONVERSATION CONTEXT:
You have access to the recent conversation history. Use it to:
- Understand follow-up questions ("what about for TIG?" after discussing MIG polarity)
- Avoid asking for info the user already provided
- Maintain coherent multi-turn conversations"""


# --- Build message history for Claude ---

def build_messages(question: str, context: str, history: list[ChatMessage] | None) -> list[dict]:
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

    # Current question always includes RAG context
    messages.append({
        "role": "user",
        "content": f"Context from manual:\n{context}\n\nQuestion: {question}"
    })

    return messages


# --- Main query endpoint ---

@app.post("/query")
async def query(request: QueryRequest):
    question_type = classify_question(request.question)

    results = collection.query(
        query_texts=[request.question],
        n_results=5
    )

    chunks = results["documents"][0]
    metadatas = results["metadatas"][0]

    context = ""
    for chunk, meta in zip(chunks, metadatas):
        source = meta.get("source", "unknown")
        page = meta.get("page", "?")
        context += f"[{source}, Page {page}]\n{chunk}\n\n"

    system_prompt = BASE_SYSTEM + "\n\n" + ARTIFACT_PROMPTS[question_type]

    messages = build_messages(request.question, context, request.history)

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=messages
    )

    answer = response.content[0].text
    return {
        "answer": answer,
        "question_type": question_type,
        "model": MODEL,
        "tokens_used": response.usage.input_tokens + response.usage.output_tokens
    }


@app.get("/health")
async def health():
    count = collection.count()
    return {
        "status": "ok",
        "model": MODEL,
        "chunks_indexed": count
    }
