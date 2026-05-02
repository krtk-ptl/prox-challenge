"""
stress_test.py — 50-question stress test for Vulcan OmniPro 220 AI Agent.
Tests for crashes, timeouts, empty responses, and artifact render errors.
Does NOT check answer correctness (that's eval.py's job).

Usage:
    python stress_test.py --api-key sk-ant-xxx
    python stress_test.py --api-key sk-ant-xxx --model claude-sonnet-4-6
    python stress_test.py --api-key sk-ant-xxx --api https://your-render-url.onrender.com
    python stress_test.py --api-key sk-ant-xxx --concurrency 3
    python stress_test.py --api-key sk-ant-xxx --start 1 --end 10   # run subset

Cost: ~$0.80-1.20 total (50 Haiku calls + 50 Sonnet responses)
"""

import json
import time
import argparse
import requests
import sys
import re
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

DEFAULT_API = "http://localhost:8000"
DEFAULT_MODEL = "claude-haiku-4-5"
DEFAULT_TIMEOUT = 90
DEFAULT_CONCURRENCY = 1  # sequential by default — safe for free-tier Render

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

# ── 50 Stress Questions ───────────────────────────────────────────────────────

QUESTIONS = [
    # --- MIG Setup (8) ---
    "How do I set up for MIG welding on 3mm mild steel?",
    "What wire size should I use for MIG welding thin sheet metal?",
    "Can I use flux core wire in MIG mode?",
    "What shielding gas do I use for MIG welding stainless?",
    "How far should the wire stick out from the tip?",
    "What does CTWD mean and why does it matter?",
    "My MIG wire keeps birds-nesting. What's causing it?",
    "How do I purge the gas line before welding?",

    # --- Polarity (7) ---
    "Which socket does the ground clamp go into for MIG?",
    "Do I need to swap cables when switching from MIG to Stick?",
    "What's the difference between DCEP and DCEN?",
    "For TIG welding aluminum, what polarity should I use?",
    "I accidentally have the cables reversed — what happens to my weld?",
    "Which terminal is positive on the OmniPro 220?",
    "If I'm using self-shielded flux core, where does the electrode cable go?",

    # --- Duty Cycle (6) ---
    "How long can I weld before I need to take a break?",
    "What happens if I exceed the duty cycle?",
    "Is the duty cycle different on 120V vs 240V?",
    "At 150 amps, what is my weld time per 10 minutes?",
    "Why did my welder shut off in the middle of a bead?",
    "What is thermal overload protection and does this welder have it?",

    # --- Troubleshooting (10) ---
    "My arc keeps going out. What should I check?",
    "The weld bead is too wide and flat — what setting do I adjust?",
    "I'm getting spatter everywhere. How do I reduce it?",
    "My stick electrode keeps sticking to the base metal.",
    "The wire is feeding but I'm not getting an arc.",
    "There's a loud popping sound when I weld. Is that normal?",
    "My weld looks like it has cracks running along it.",
    "The welder turns on but the wire won't feed.",
    "I'm getting undercut on my welds. What's wrong?",
    "My welds are brown and discolored instead of shiny silver.",

    # --- Settings (8) ---
    "What voltage should I set for welding 1/4 inch steel with MIG?",
    "Give me Stick welding settings for 6013 electrode on 3/16 steel.",
    "What wire speed setting for 0.030 wire on 18 gauge sheet?",
    "What's the maximum thickness this welder can handle?",
    "Can I weld aluminum with this machine?",
    "What gas flow rate should I set for MIG welding?",
    "Is this welder suitable for welding roll cage tubing?",
    "What amperage for TIG welding 1/8 inch stainless?",

    # --- General / Safety (6) ---
    "Is it safe to weld near a gas cylinder?",
    "Do I need a special outlet for 240V operation?",
    "How do I store the welder when not in use?",
    "What maintenance should I do after every use?",
    "Can two people use the welder at the same time?",
    "What's the warranty on this welder?",

    # --- Edge cases / Stress (5) ---
    "What settings should I use?",                     # vague — should ask clarification
    "It's not working.",                               # vague — should ask for symptom
    "How does welding work?",                          # very general
    "Can I use this to cut metal instead of weld?",   # off-scope
    "What is the meaning of life?",                   # completely off-topic
]

assert len(QUESTIONS) == 50, f"Expected 50 questions, got {len(QUESTIONS)}"


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class TestResult:
    index: int
    question: str
    passed: bool
    failure_reason: str = ""
    question_type: str = ""
    response_len: int = 0
    tokens: int = 0
    elapsed: float = 0.0
    has_artifact: bool = False
    artifact_error: bool = False
    response_text: str = ""          # ADDED: store actual response for debugging


# ── Fetch ─────────────────────────────────────────────────────────────────────

def fetch(api_url: str, question: str, timeout: int, api_key: str, model: str) -> dict:
    payload = {"question": question, "history": []}
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key,
        "X-Model": model,
    }
    start = time.time()

    res = requests.post(
        f"{api_url}/query",
        json=payload,
        headers=headers,
        stream=True,
        timeout=timeout,
    )
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

    return {
        "text": accumulated,
        "question_type": question_type,
        "tokens": tokens_used,
        "elapsed": round(time.time() - start, 1),
    }


# ── Checker ───────────────────────────────────────────────────────────────────

def check(index: int, question: str, result: dict) -> TestResult:
    text = result["text"]
    artifact_match = re.search(r'<artifact type="react">([\s\S]*?)</artifact>', text)
    has_artifact = artifact_match is not None
    artifact_error = False

    if not text or len(text.strip()) < 30:
        return TestResult(index=index, question=question, passed=False,
                          failure_reason="empty or near-empty response",
                          question_type=result["question_type"],
                          response_len=len(text), tokens=result["tokens"],
                          elapsed=result["elapsed"],
                          response_text=text)          # ADDED

    # Strip artifact code before checking error markers
    text_only = re.sub(r'<artifact type="react">[\s\S]*?</artifact>', '', text)

    error_markers = ["connection error", "server error", "internal server error", "traceback", "exception occurred"]
    for marker in error_markers:
        if marker in text_only.lower():
            return TestResult(index=index, question=question, passed=False,
                              failure_reason=f"error marker in response: '{marker}'",
                              question_type=result["question_type"],
                              response_len=len(text), tokens=result["tokens"],
                              elapsed=result["elapsed"],
                              response_text=text)      # ADDED

    if has_artifact:
        code = artifact_match.group(1)
        open_braces = code.count("{")
        close_braces = code.count("}")
        open_parens = code.count("(")
        close_parens = code.count(")")
        if abs(open_braces - close_braces) > 3:
            artifact_error = True
        if abs(open_parens - close_parens) > 3:
            artifact_error = True
        if artifact_error:
            return TestResult(index=index, question=question, passed=False,
                              failure_reason=f"artifact brace mismatch: {{{open_braces}/{close_braces}}} ({open_parens}/{close_parens})",
                              question_type=result["question_type"],
                              response_len=len(text), tokens=result["tokens"],
                              elapsed=result["elapsed"], has_artifact=True,
                              artifact_error=True,
                              response_text=text)      # ADDED

    return TestResult(
        index=index, question=question, passed=True,
        question_type=result["question_type"],
        response_len=len(text), tokens=result["tokens"],
        elapsed=result["elapsed"], has_artifact=has_artifact,
    )


# ── Runner ────────────────────────────────────────────────────────────────────

def run_single(args_tuple) -> TestResult:
    index, question, api_url, timeout, api_key, model = args_tuple
    try:
        result = fetch(api_url, question, timeout, api_key, model)
        return check(index, question, result)
    except requests.exceptions.Timeout:
        return TestResult(index=index, question=question, passed=False,
                          failure_reason=f"timeout after {timeout}s")
    except requests.exceptions.ConnectionError as e:
        return TestResult(index=index, question=question, passed=False,
                          failure_reason=f"connection error: {e}")
    except Exception as e:
        return TestResult(index=index, question=question, passed=False,
                          failure_reason=f"unexpected error: {e}")


# ── Reporter ──────────────────────────────────────────────────────────────────

def print_summary(results: list[TestResult], total_time: float):
    passed = [r for r in results if r.passed]
    failed = [r for r in results if not r.passed]
    artifact_count = sum(1 for r in results if r.has_artifact)
    total_tokens = sum(r.tokens for r in results)
    avg_elapsed = sum(r.elapsed for r in results) / len(results) if results else 0

    by_type: dict[str, list[TestResult]] = {}
    for r in results:
        by_type.setdefault(r.question_type, []).append(r)

    bar_filled = "█" * len(passed)
    bar_empty  = "░" * len(failed)

    print(f"\n{'─'*65}")
    print(f"{BOLD}STRESS TEST SUMMARY{RESET}")
    print(f"{'─'*65}")
    print(f"  Score:     {BOLD}{len(passed)}/{len(results)}{RESET}  {bar_filled}{bar_empty}")
    print(f"  Tokens:    {total_tokens:,} (~${total_tokens * 0.000015:.2f})")
    print(f"  Avg time:  {avg_elapsed:.1f}s per question")
    print(f"  Total:     {total_time:.0f}s wall clock")
    print(f"  Artifacts: {artifact_count} generated")

    print(f"\n  {BOLD}By category:{RESET}")
    for qtype, type_results in sorted(by_type.items()):
        type_passed = sum(1 for r in type_results if r.passed)
        print(f"    {qtype:12s}  {type_passed}/{len(type_results)}")

    if failed:
        print(f"\n  {RED}{BOLD}Failures:{RESET}")
        for r in failed:
            q_preview = r.question[:55] + ("..." if len(r.question) > 55 else "")
            print(f"    [{r.index+1:02d}] {RED}FAIL{RESET} {q_preview}")
            print(f"         {r.failure_reason}")
            if r.response_text:                        # ADDED: print actual response
                preview = r.response_text[:400].replace("\n", " ")
                print(f"         {YELLOW}Response: {preview}{RESET}")

    print(f"\n{'─'*65}")
    if not failed:
        print(f"{GREEN}{BOLD}All {len(results)} tests passed.{RESET}")
    else:
        print(f"{RED}{len(failed)} failed.{RESET} Fix failures above before submitting.")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Stress test for Vulcan OmniPro 220 agent")
    parser.add_argument("--api", default=DEFAULT_API, help="Backend URL (default: localhost:8000)")
    parser.add_argument("--api-key", default=os.getenv("ANTHROPIC_API_KEY"), help="Anthropic API key (or set ANTHROPIC_API_KEY env var)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Model to test with (default: {DEFAULT_MODEL})")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--start", type=int, default=1, help="Start from question N (1-indexed)")
    parser.add_argument("--end", type=int, default=50, help="End at question N (1-indexed)")
    args = parser.parse_args()

    if not args.api_key:
        print(f"{RED}Error: No API key provided. Use --api-key sk-ant-xxx or set ANTHROPIC_API_KEY env var.{RESET}")
        sys.exit(1)

    questions_to_run = [(i, q) for i, q in enumerate(QUESTIONS)
                        if args.start <= i+1 <= args.end]

    print(f"\n{BOLD}Vulcan OmniPro 220 — Stress Test{RESET}")
    print(f"API:   {args.api}")
    print(f"Model: {args.model}")
    print(f"Questions: {len(questions_to_run)} | Concurrency: {args.concurrency} | Timeout: {args.timeout}s\n")

    try:
        health = requests.get(f"{args.api}/health", timeout=10).json()
        print(f"  Backend: {GREEN}online{RESET} | model={health.get('model')} | chunks={health.get('chunks_indexed')}\n")
    except Exception:
        print(f"  {YELLOW}Warning: /health check failed{RESET}\n")

    wall_start = time.time()
    results: list[TestResult] = [None] * len(questions_to_run)  # type: ignore
    task_args = [(i, q, args.api, args.timeout, args.api_key, args.model) for i, q in questions_to_run]

    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = {executor.submit(run_single, ta): idx for idx, ta in enumerate(task_args)}
        for future in as_completed(futures):
            idx = futures[future]
            result = future.result()
            results[idx] = result
            status = f"{GREEN}PASS{RESET}" if result.passed else f"{RED}FAIL{RESET}"
            q_preview = result.question[:50] + ("..." if len(result.question) > 50 else "")
            artifact_tag = f" {CYAN}[artifact]{RESET}" if result.has_artifact else ""
            print(f"  [{result.index+1:02d}] {status} {result.elapsed:5.1f}s  {q_preview}{artifact_tag}")
            if not result.passed:
                print(f"       {RED}{result.failure_reason}{RESET}")

    wall_time = time.time() - wall_start
    print_summary(results, wall_time)

    if any(not r.passed for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
