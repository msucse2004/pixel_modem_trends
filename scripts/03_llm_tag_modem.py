"""
Step 3: Call local Ollama to tag posts with modem-related issue signals.
Reads data/parsed/posts.jsonl, writes data/llm/modem_tags.jsonl.
Resume-safe (skips post_id already in output). Windows-friendly, no external APIs.
"""
import argparse
import json
import platform
import re
import time
from pathlib import Path

import requests

from _utils import get_logger, project_root

OLLAMA_URL = "http://localhost:11434/api/generate"


def get_default_model() -> str:
    """Windows: gemma3, Linux: gemma3:27b"""
    return "gemma3" if platform.system() == "Windows" else "gemma3:27b"
RATE_LIMIT_SLEEP = 0.2

ALLOWED_SYMPTOMS = {
    "lost_connectivity", "no_service", "missed_calls", "stuck_lte", "stuck_5g",
    "roaming_handoff", "low_signal", "slow_data_latency",
}
ALLOWED_SEVERITY = {"low", "medium", "high"}
ALLOWED_CONNECTIVITY_TYPE = {"cellular", "wifi", "both", "unknown"}
ALLOWED_AFTER_UPDATE = {"yes", "no", "unknown"}

# Keywords to pick relevant comment lines (top 5)
MODEM_KEYWORDS = (
    "modem", "connectivity", "signal", "5g", "lte", "dropped", "service",
    "missed call", "roaming", "handoff", "latency", "cellular", "network",
    "sim", "antenna", "data", "connection", "bars", "reception",
)


def load_prompt_template(root: Path) -> str:
    path = root / "scripts" / "prompts" / "modem_prompt.txt"
    return path.read_text(encoding="utf-8")


MAX_BODY_CHARS = 5000
MAX_KEYWORD_COMMENT_LINES = 10


def build_input_text(post: dict) -> str:
    """Full post body (up to MAX_BODY_CHARS) + comment lines with modem keywords for accurate tagging."""
    body = (post.get("body_text") or "").strip()
    comments = (post.get("comments_text") or "").strip()
    if not body and post.get("raw_text_cleaned"):
        body = (post.get("raw_text_cleaned") or "").strip()
    if len(body) > MAX_BODY_CHARS:
        body = body[:MAX_BODY_CHARS] + "\n[... truncated ...]"
    lines = body.split("\n") if body else []
    if comments:
        comment_lines = [ln.strip() for ln in comments.split("\n") if ln.strip()]
        keyword_lines = [ln for ln in comment_lines if any(kw in ln.lower() for kw in MODEM_KEYWORDS)]
        for ln in keyword_lines[:MAX_KEYWORD_COMMENT_LINES]:
            lines.append(ln)
    return "\n".join(lines).strip() or "(no text)"


def existing_post_ids(out_path: Path) -> set[str]:
    """Post IDs already in output file (for resume)."""
    if not out_path.exists():
        return set()
    seen = set()
    with open(out_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if rec.get("post_id"):
                    seen.add(rec["post_id"])
            except Exception:
                pass
    return seen


def call_ollama(prompt: str, model: str, log) -> str:
    """POST to Ollama /api/generate, return full response text."""
    try:
        r = requests.post(
            OLLAMA_URL,
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=120,
        )
        r.raise_for_status()
        out = r.json().get("response") or ""
        return out.strip()
    except requests.RequestException as e:
        log.error("Ollama request failed: %s", e)
        raise


def extract_json_from_response(raw: str) -> dict | None:
    """Parse JSON from model output; strip markdown code block if present."""
    raw = raw.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
    if m:
        raw = m.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to find first { ... } block
        start = raw.find("{")
        if start == -1:
            return None
        depth = 0
        for i in range(start, len(raw)):
            if raw[i] == "{":
                depth += 1
            elif raw[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(raw[start : i + 1])
                    except json.JSONDecodeError:
                        return None
        return None


def normalize_record(parsed: dict, post_id: str) -> dict:
    """Ensure output matches schema; default unknown where missing."""
    is_modem = bool(parsed.get("is_modem_issue"))
    symptoms = parsed.get("symptoms")
    if not isinstance(symptoms, list):
        symptoms = []
    symptoms = [s for s in symptoms if s in ALLOWED_SYMPTOMS]
    if not is_modem:
        symptoms = []

    severity = (parsed.get("severity") or "low").lower()
    if severity not in ALLOWED_SEVERITY:
        severity = "low"
    if not is_modem:
        severity = "low"

    conn_type = (parsed.get("connectivity_type") or "unknown").lower()
    if conn_type not in ALLOWED_CONNECTIVITY_TYPE:
        conn_type = "unknown"

    after = (parsed.get("after_update") or "unknown").lower()
    if after not in ALLOWED_AFTER_UPDATE:
        after = "unknown"

    evidence = parsed.get("evidence")
    if not isinstance(evidence, list):
        evidence = []
    evidence = [str(e).strip() for e in evidence if e]

    # issue_descriptions: symptom -> one-sentence description (for product improvement)
    issue_descriptions = parsed.get("issue_descriptions")
    if not isinstance(issue_descriptions, dict):
        issue_descriptions = {}
    issue_descriptions = {
        str(k).strip(): str(v).strip()[:500]
        for k, v in issue_descriptions.items()
        if k in ALLOWED_SYMPTOMS and v
    }
    # Keep only descriptions for symptoms we actually have
    issue_descriptions = {s: issue_descriptions[s] for s in symptoms if s in issue_descriptions}

    return {
        "post_id": post_id,
        "is_modem_issue": bool(parsed.get("is_modem_issue")),
        "severity": severity,
        "symptoms": symptoms,
        "issue_descriptions": issue_descriptions,
        "connectivity_type": conn_type,
        "after_update": after,
        "carrier": (parsed.get("carrier") or "unknown").strip(),
        "device": (parsed.get("device") or "unknown").strip(),
        "evidence": evidence[:10],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Tag posts with modem issue signals via local Ollama.")
    parser.add_argument("--model", default=None, help="Ollama model name (default: gemma3 on Windows, gemma3:27b on Linux)")
    parser.add_argument("--max_posts", type=int, default=None, help="Max number of posts to process")
    parser.add_argument("--only_subreddits", type=str, default=None, help="Comma-separated subreddit names to include")
    parser.add_argument("--retag", action="store_true", help="Re-tag all posts (clear output and run; use to get issue_descriptions)")
    args = parser.parse_args()
    args.model = args.model or get_default_model()

    root = project_root()
    log = get_logger("llm_tag_modem")

    posts_path = root / "data" / "parsed" / "posts.jsonl"
    out_path = root / "data" / "llm" / "modem_tags.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not posts_path.exists():
        log.warning("No posts file: %s", posts_path)
        print("No posts to process. Run step 2 first.")
        return

    posts = []
    with open(posts_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                posts.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    only_subs = None
    if args.only_subreddits:
        only_subs = {s.strip().lower() for s in args.only_subreddits.split(",") if s.strip()}
    if only_subs:
        posts = [p for p in posts if (p.get("subreddit") or "").lower() in only_subs]

    if args.max_posts is not None:
        posts = posts[: args.max_posts]

    if args.retag:
        seen = set()
        if out_path.exists():
            out_path.write_text("", encoding="utf-8")
            log.info("Cleared output for --retag; will process all %d posts", len(posts))
    else:
        seen = existing_post_ids(out_path)
    to_process = [p for p in posts if p.get("post_id") and p["post_id"] not in seen]
    log.info("Posts to process: %d (skipped %d already in output)", len(to_process), len(posts) - len(to_process))

    if not to_process:
        print("No new posts to tag. Exiting.")
        return

    template = load_prompt_template(root)
    appended = 0
    mode = "w" if args.retag else "a"
    with open(out_path, mode, encoding="utf-8") as out_file:
        for i, post in enumerate(to_process):
            post_id = post.get("post_id") or ""
            input_text = build_input_text(post)
            prompt = template.replace("{{POST_ID}}", post_id).replace("{{INPUT_TEXT}}", input_text)

            try:
                response_text = call_ollama(prompt, args.model, log)
                time.sleep(RATE_LIMIT_SLEEP)
            except Exception:
                log.exception("Skipping post_id=%s after Ollama error", post_id)
                continue

            rec = extract_json_from_response(response_text)
            if not rec:
                log.warning("No valid JSON for post_id=%s", post_id)
                continue

            rec["post_id"] = post_id
            out_rec = normalize_record(rec, post_id)
            out_file.write(json.dumps(out_rec, ensure_ascii=False) + "\n")
            out_file.flush()
            appended += 1
            log.info("[%d/%d] Tagged post_id=%s is_modem_issue=%s", i + 1, len(to_process), post_id, out_rec["is_modem_issue"])

    print("\nTagged %d posts. Output: %s" % (appended, out_path))

    # Print first few outputs from this run (last N written)
    if appended:
        print("\n--- Sample tagged output (last 1-2 in this run) ---")
        with open(out_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for line in lines[-2:]:
            line = line.strip()
            if line:
                print(json.dumps(json.loads(line), ensure_ascii=True, indent=2))
        print("---")


if __name__ == "__main__":
    main()
