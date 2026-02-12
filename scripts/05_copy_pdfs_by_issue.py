"""
Step 5: Create by-issue folders and copy original PDFs.
Uses modem_issues_report classification: for each symptom in modem_issue_summary,
creates data/out/by_issue/{symptom}/ and copies PDFs of posts with that issue.
Requires: posts.jsonl (post_id -> source_file), posts_modem_long.csv (post_id, symptom, is_modem_issue).
"""
import csv
import json
import re
import shutil
from pathlib import Path

from _utils import get_logger, project_root


def load_posts(path: Path) -> dict[str, dict]:
    """Load posts.jsonl by post_id."""
    out = {}
    if not path.exists():
        return out
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                pid = rec.get("post_id")
                if pid:
                    out[pid] = rec
            except json.JSONDecodeError:
                pass
    return out


def load_modem_long(path: Path) -> list[dict]:
    """Load posts_modem_long.csv; return rows with is_modem_issue=True and symptom != 'none'."""
    if not path.exists():
        return []
    rows = []
    with open(path, "r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            if not (row.get("is_modem_issue", "").lower() in ("true", "1") or row.get("is_modem_issue") is True):
                continue
            symptom = (row.get("symptom") or "").strip()
            if not symptom or symptom.lower() == "none":
                continue
            rows.append(row)
    return rows


def find_pdf_path(pdfs_dir: Path, source_file: str) -> Path | None:
    """Resolve PDF path from source_file (TXT filename). PDF has same stem as TXT."""
    if not source_file:
        return None
    stem = source_file
    if stem.lower().endswith(".txt"):
        stem = stem[:-4]
    # Try exact stem first
    pdf_path = pdfs_dir / (stem + ".pdf")
    if pdf_path.exists():
        return pdf_path
    # Fallback: some TXTs have date prefix (YYYY-MM-DD_) but PDFs may not
    m = re.match(r"^\d{4}-\d{2}-\d{2}_(.+)$", stem)
    if m:
        alt_stem = m.group(1)
        pdf_path = pdfs_dir / (alt_stem + ".pdf")
        if pdf_path.exists():
            return pdf_path
    return None


def main() -> None:
    root = project_root()
    log = get_logger("copy_pdfs_by_issue")

    posts_path = root / "data" / "parsed" / "posts.jsonl"
    long_path = root / "data" / "out" / "posts_modem_long.csv"
    pdfs_dir = root / "data" / "pdfs"
    out_base = root / "data" / "out" / "by_issue"

    posts = load_posts(posts_path)
    modem_rows = load_modem_long(long_path)

    if not modem_rows:
        log.warning("No modem-issue rows in %s", long_path)
        print("No modem issues to copy. Run step 04 first.")
        return

    # (symptom, post_id) -> avoid duplicate copies
    copied = set()
    stats: dict[str, int] = {}

    for row in modem_rows:
        post_id = row.get("post_id") or ""
        symptom = (row.get("symptom") or "").strip()
        if not symptom or symptom.lower() == "none":
            continue

        key = (symptom, post_id)
        if key in copied:
            continue
        copied.add(key)

        post = posts.get(post_id)
        if not post:
            log.warning("Post not found: %s", post_id)
            continue

        source_file = post.get("source_file") or ""
        pdf_src = find_pdf_path(pdfs_dir, source_file)
        if not pdf_src:
            log.warning("PDF not found for post_id=%s source_file=%s", post_id, source_file)
            continue

        symptom_dir = out_base / symptom
        symptom_dir.mkdir(parents=True, exist_ok=True)
        dest = symptom_dir / pdf_src.name
        shutil.copy2(pdf_src, dest)
        stats[symptom] = stats.get(symptom, 0) + 1
        log.debug("Copied %s -> %s", pdf_src.name, dest)

    for symptom, count in sorted(stats.items(), key=lambda x: -x[1]):
        print("  %s: %d PDFs" % (symptom, count))

    print("\nCopied PDFs to %s (by issue)" % out_base)


if __name__ == "__main__":
    main()
