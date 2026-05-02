"""
eval.py — Evaluation script for Vulcan OmniPro 220 AI Agent
Two-layer grading:
  Layer 1 (keyword): fast, free — checks classifier category + required keywords
  Layer 2 (LLM judge): Claude Haiku reads ground truth + agent response, gives
                        PASS/FAIL with reasoning. Catches paraphrased correct
                        answers and subtle hallucinations that keywords miss.

Usage:
    python eval.py --api-key sk-ant-xxx                        # keyword only
    python eval.py --api-key sk-ant-xxx --judge                # + LLM judge (~$0.05 extra)
    python eval.py --api-key sk-ant-xxx --model claude-sonnet-4-6
    python eval.py --api-key sk-ant-xxx --api https://render-url
    python eval.py --api-key sk-ant-xxx --test T2 --judge      # single test
    python eval.py --api-key sk-ant-xxx --verbose              # show all check details

Cost with --judge: ~$0.10-0.15 total (6 agent calls + 6 judge calls, all Haiku)
"""

import json
import time
import argparse
import requests
import sys
import re
import os
from dotenv import load_dotenv

load_dotenv()

DEFAULT_API = "http://localhost:8000"
DEFAULT_MODEL = "claude-haiku-4-5"
JUDGE_MODEL = "claude-haiku-4-5"

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


# ── Ground Truth ──────────────────────────────────────────────────────────────
# Sourced directly from Vulcan OmniPro 220 manual PDFs.
# Used by the LLM judge to evaluate agent responses.

GROUND_TRUTH = {
    "T1": """
Duty cycle for MIG welding at 200A on 240V is 25%.
In a 10-minute period: weld for 2.5 minutes, then rest for 7.5 minutes.
100% continuous welding is only possible at 115A on 240V.
Source: Manual page 7 (specifications) and page 19 (duty cycle section).
""",
    "T2": """
TIG welding on the OmniPro 220 uses DCEN (Direct Current Electrode Negative).
The TIG torch connects to the negative terminal.
The ground clamp connects to the positive terminal.
Shielding gas is 100% Argon at 10-25 SCFH.
Source: TIG Welding section page 30, polarity diagram.
""",
    "T3": """
Porosity (small holes or bubbles) in MIG welds is caused by (from manual page 37):
1. Incorrect polarity — must be DCEP for MIG.
2. Insufficient shielding gas — empty bottle, wrong flow rate, or clogged nozzle.
3. Incorrect shielding gas type — use gas recommended by wire supplier.
4. Dirty workpiece or welding wire — clean to bare metal, wire must be rust-free.
5. Inconsistent travel speed — maintain steady travel.
6. CTWD too long — maintain contact tip to work distance under 1/2 inch.
A correct answer must mention shielding gas AND at least one other cause from this list.
""",
    "T4": """
The manual does not contain explicit voltage/wire speed numbers for 1/8 inch mild steel in text.
The machine uses a built-in settings chart (inside welder door) and LCD auto-recommendation system.
The user selects wire diameter and material thickness via the knobs, and the machine recommends settings.
A correct answer either: (a) gives plausible values from the selection chart, OR (b) explains that
the machine auto-recommends settings and instructs the user to use the LCD system with the knobs.
A wrong answer deflects entirely without giving any guidance.
""",
    "T5": """
Flux-Core (gasless) welding on the OmniPro 220 uses DCEN (Direct Current Electrode Negative).
Work clamp (ground) connects to the POSITIVE (+) socket.
Wire Feed Power Cable (electrode) connects to the NEGATIVE (-) socket.
This is the opposite of solid core MIG which uses DCEP.
Source: Manual page 13, step 16.
""",
    "T6": """
The question is too vague to answer without clarification.
A correct response asks for ALL THREE of: (1) welding process (MIG/TIG/Stick/Flux-Core),
(2) material type, and (3) material thickness.
The machine requires all three inputs to recommend settings via its LCD knob system.
An answer that only asks about process without material and thickness is incomplete.
""",
}


# ── Test Suite ────────────────────────────────────────────────────────────────

TESTS = [
    {
        "id": "T1",
        "description": "Duty cycle at 200A on 240V — exact manual value",
        "question": "What is the duty cycle for MIG welding at 200A on 240V?",
        "expected_type": "duty_cycle",
        "must_contain": ["25%", "200"],
        "must_not_contain": ["50%", "30%"],
    },
    {
        "id": "T2",
        "description": "TIG polarity — torch goes to negative terminal (DCEN)",
        "question": "What polarity do I use for TIG welding on the OmniPro 220?",
        "expected_type": "polarity",
        "must_contain": ["dcen", "negative"],
        "must_not_contain": ["positive electrode"],
    },
    {
        "id": "T3",
        "description": "Porosity troubleshooting — must list shielding gas + other causes",
        "question": "My MIG welds have small holes and bubbles in them. What am I doing wrong?",
        "expected_type": "troubleshoot",
        "must_contain": ["gas", "porosity"],
        "must_not_contain": [],
    },
    {
        "id": "T4",
        "description": "Settings for 1/8 inch mild steel — give guidance, not deflect",
        "question": "What voltage and wire speed should I use for MIG welding 1/8 inch mild steel?",
        "expected_type": "settings",
        "must_contain": ["voltage", "wire"],
        "must_not_contain": ["i don't know", "cannot determine", "consult a professional"],
    },
    {
        "id": "T5",
        "description": "Flux-Core polarity — work clamp to positive, wire to negative (DCEN)",
        "question": "For flux core welding, do I connect my work clamp to positive or negative?",
        "expected_type": "polarity",
        "must_contain": ["positive", "dcen"],
        "must_not_contain": [],
    },
    {
        "id": "T6",
        "description": "Ambiguity — must ask for process, material, AND thickness",
        "question": "What settings should I use?",
        "expected_type": "settings",
        "must_contain": ["process", "material", "thickness"],
        "must_not_contain": [],
    },
]


# ── Agent fetch ───────────────────────────────────────────────────────────────

def fetch_agent_response(api_url: str, question: str, api_key: str, model: str) -> dict:
    payload = {"question": question, "history": []}
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key,
        "X-Model": model,
    }
    start = time.time()

    res = requests.post(f"{api_url}/query", json=payload, headers=headers, stream=True, timeout=90)
    res.raise_for_status()

    accumulated = ""
    question_type = "unknown"
    tokens_used = 0
    buffer = ""

    for chunk in res.iter_content(chunk_size=None):
        buffer += chunk.decode("utf-8", errors="replace")
        lines = buffer.split("\n")
        buffer = lines.pop()
        for line in lines:
            if not line.startswith("data: "):
                continue
            raw = line[6:].strip()
            if not raw:
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "token":
                accumulated += event.get("text", "")
            elif event.get("type") == "metadata":
                question_type = event.get("question_type", "unknown")
            elif event.get("type") == "done":
                tokens_used = event.get("tokens_used", 0)

    clean = re.sub(r'<artifact type="react">[\s\S]*?</artifact>', "", accumulated).strip()

    return {
        "text": clean,
        "question_type": question_type,
        "tokens_used": tokens_used,
        "elapsed_sec": round(time.time() - start, 1),
    }


# ── LLM Judge ─────────────────────────────────────────────────────────────────

JUDGE_SYSTEM = """You are an objective evaluator for a welding assistant AI.
You will receive a question, the correct answer from the official manual, and the agent's response.

Decide if the agent response is CORRECT or INCORRECT based on these rules:
- CORRECT: agent agrees with the manual on the key facts, even if phrased differently.
  Partial answers that cover the main point count as CORRECT.
- INCORRECT: agent states something that contradicts the manual, gives clearly wrong
  numbers/values, or completely deflects without any useful guidance.
- If the ground truth says a clarifying question is required, CORRECT means the agent
  asked for the required information.
- Ignore style, formatting, and minor omissions of secondary details.

Respond ONLY with this JSON, no markdown fences, no extra text:
{"verdict": "CORRECT", "reason": "one sentence"}
or
{"verdict": "INCORRECT", "reason": "one sentence"}"""


def llm_judge(question: str, ground_truth: str, agent_response: str, api_key: str) -> dict:
    if not api_key:
        return {"verdict": "SKIP", "reason": "No API key provided", "tokens": 0}

    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)

        user_msg = f"""QUESTION: {question}

CORRECT ANSWER (from Vulcan OmniPro 220 manual):
{ground_truth.strip()}

AGENT RESPONSE:
{agent_response[:2000]}"""

        resp = client.messages.create(
            model=JUDGE_MODEL,
            max_tokens=120,
            system=JUDGE_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = resp.content[0].text.strip()
        raw = re.sub(r"```json|```", "", raw).strip()
        result = json.loads(raw)
        return {
            "verdict": result.get("verdict", "SKIP"),
            "reason": result.get("reason", ""),
            "tokens": resp.usage.input_tokens + resp.usage.output_tokens,
        }
    except Exception as e:
        return {"verdict": "SKIP", "reason": f"Judge error: {e}", "tokens": 0}


# ── Keyword grader ────────────────────────────────────────────────────────────

def keyword_grade(test: dict, result: dict) -> dict:
    text_lower = result["text"].lower()
    checks = []

    type_ok = result["question_type"] == test["expected_type"]
    checks.append({
        "name": "classifier",
        "passed": type_ok,
        "detail": f"got '{result['question_type']}', expected '{test['expected_type']}'",
    })

    for kw in test["must_contain"]:
        found = kw.lower() in text_lower
        checks.append({"name": f"contains '{kw}'", "passed": found,
                        "detail": "found" if found else f"MISSING '{kw}'"})

    for kw in test["must_not_contain"]:
        absent = kw.lower() not in text_lower
        checks.append({"name": f"not_contains '{kw}'", "passed": absent,
                        "detail": "absent (good)" if absent else f"FOUND (bad): '{kw}'"})

    length_ok = len(result["text"]) > 100
    checks.append({"name": "response_length", "passed": length_ok,
                    "detail": f"{len(result['text'])} chars"})

    return {"passed": all(c["passed"] for c in checks), "checks": checks}


# ── Reporter ──────────────────────────────────────────────────────────────────

def print_result(test: dict, result: dict, kw: dict, judge: dict | None, verbose: bool):
    judge_pass = (judge["verdict"] == "CORRECT") if (judge and judge["verdict"] != "SKIP") else True
    overall = kw["passed"] and judge_pass

    status = f"{GREEN}PASS{RESET}" if overall else f"{RED}FAIL{RESET}"
    print(f"\n{BOLD}[{test['id']}] {test['description']}{RESET}")
    print(f"  Status:  {status}  |  {result['elapsed_sec']}s  |  {result['tokens_used']} tokens")

    kw_label = f"{GREEN}PASS{RESET}" if kw["passed"] else f"{RED}FAIL{RESET}"
    print(f"  Keyword: {kw_label}")
    if not kw["passed"] or verbose:
        for c in kw["checks"]:
            icon = f"{GREEN}checkmark{RESET}" if c["passed"] else f"{RED}x{RESET}"
            print(f"    {icon}  {c['name']}: {c['detail']}")

    if judge:
        if judge["verdict"] == "SKIP":
            print(f"  Judge:   {YELLOW}SKIP{RESET} — {judge['reason']}")
        else:
            color = GREEN if judge_pass else RED
            print(f"  Judge:   {color}{judge['verdict']}{RESET} — {judge['reason']} ({judge.get('tokens', 0)} tokens)")

    if not overall or verbose:
        preview = result["text"][:300].replace("\n", " ")
        print(f"\n  {CYAN}Response:{RESET} {preview}...")


def print_summary(rows: list[dict], use_judge: bool):
    passed = sum(1 for r in rows if r["passed"])
    total = len(rows)
    agent_tokens = sum(r["tokens"] for r in rows)
    judge_tokens = sum(r.get("judge_tokens", 0) for r in rows)
    all_tokens = agent_tokens + judge_tokens

    bar = "█" * passed + "░" * (total - passed)
    print(f"\n{'─'*60}")
    print(f"{BOLD}EVAL SUMMARY{RESET}")
    print(f"{'─'*60}")
    print(f"  Score:        {BOLD}{passed}/{total}{RESET}  {bar}")
    print(f"  Agent tokens: {agent_tokens:,}")
    if use_judge:
        print(f"  Judge tokens: {judge_tokens:,}")
    print(f"  Est. cost:    ~${all_tokens * 0.000001:.4f}")
    print(f"{'─'*60}")
    if passed == total:
        print(f"\n{GREEN}{BOLD}All tests passed.{RESET}")
    else:
        failed_ids = [r["id"] for r in rows if not r["passed"]]
        print(f"\n{RED}Failed: {', '.join(failed_ids)}{RESET}")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Eval for Vulcan OmniPro 220 agent")
    parser.add_argument("--api", default=DEFAULT_API, help="Backend URL (default: localhost:8000)")
    parser.add_argument("--api-key", default=os.getenv("ANTHROPIC_API_KEY"), help="Anthropic API key (or set ANTHROPIC_API_KEY env var)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Model to test with (default: {DEFAULT_MODEL})")
    parser.add_argument("--judge", action="store_true", help="Enable LLM-as-judge grading")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--test", help="Run one test only, e.g. --test T2")
    args = parser.parse_args()

    if not args.api_key:
        print(f"{RED}Error: No API key provided. Use --api-key sk-ant-xxx or set ANTHROPIC_API_KEY env var.{RESET}")
        sys.exit(1)

    tests = TESTS if not args.test else [t for t in TESTS if t["id"] == args.test.upper()]
    if not tests:
        print(f"{RED}No test found: '{args.test}'{RESET}")
        sys.exit(1)

    mode = "keyword + LLM judge" if args.judge else "keyword only (use --judge for LLM grading)"
    print(f"\n{BOLD}Vulcan OmniPro 220 — Agent Eval{RESET}")
    print(f"Mode:  {mode}")
    print(f"API:   {args.api}")
    print(f"Model: {args.model}\n")

    try:
        health = requests.get(f"{args.api}/health", timeout=10).json()
        print(f"  Backend: {GREEN}online{RESET} | model={health.get('model')} | chunks={health.get('chunks_indexed')}\n")
    except Exception:
        print(f"  {YELLOW}Warning: /health check failed{RESET}\n")

    summary_rows = []

    for test in tests:
        print(f"  Running {test['id']}: {test['description'][:55]}...", end="", flush=True)

        try:
            result = fetch_agent_response(args.api, test["question"], args.api_key, args.model)
        except Exception as e:
            print(f" {RED}ERROR: {e}{RESET}")
            summary_rows.append({"id": test["id"], "passed": False, "tokens": 0, "judge_tokens": 0})
            continue

        print(f" done ({result['elapsed_sec']}s)")

        kw = keyword_grade(test, result)

        judge_result = None
        judge_tokens = 0
        if args.judge:
            print(f"    Judging {test['id']}...", end="", flush=True)
            judge_result = llm_judge(test["question"], GROUND_TRUTH[test["id"]], result["text"], args.api_key)
            judge_tokens = judge_result.get("tokens", 0)
            print(f" {judge_result['verdict']} ({judge_tokens} tokens)")

        judge_pass = (judge_result["verdict"] == "CORRECT") if (judge_result and judge_result["verdict"] != "SKIP") else True
        overall = kw["passed"] and judge_pass

        print_result(test, result, kw, judge_result, args.verbose)
        summary_rows.append({
            "id": test["id"],
            "passed": overall,
            "tokens": result["tokens_used"],
            "judge_tokens": judge_tokens,
        })

    print_summary(summary_rows, args.judge)
    if not all(r["passed"] for r in summary_rows):
        sys.exit(1)


if __name__ == "__main__":
    main()
