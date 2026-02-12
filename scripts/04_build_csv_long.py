"""
Step 4: Join posts + modem_tags and output long-format CSV for R,
plus aggregated monthly symptom counts.
"""
import csv
import json
from pathlib import Path
from collections import defaultdict

from _utils import get_logger, project_root

LONG_COLUMNS = [
    "post_id", "subreddit", "created_at_local", "created_date", "created_month",
    "title", "url", "is_modem_issue", "severity", "symptom", "issue_description",
    "connectivity_type", "after_update", "carrier", "device",
    "evidence_1", "evidence_2", "evidence_3",
]


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


def load_tags(path: Path) -> dict[str, dict]:
    """Load modem_tags.jsonl by post_id."""
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


def build_long_rows(posts: dict[str, dict], tags: dict[str, dict]) -> list[dict]:
    """One row per (post_id, symptom); if symptoms empty, one row with symptom='none'."""
    rows = []
    for post_id, tag in tags.items():
        post = posts.get(post_id)
        if not post:
            continue
        symptoms = tag.get("symptoms") or []
        if not symptoms:
            symptoms = ["none"]
        evidence = tag.get("evidence") or []
        e1 = evidence[0] if len(evidence) > 0 else ""
        e2 = evidence[1] if len(evidence) > 1 else ""
        e3 = evidence[2] if len(evidence) > 2 else ""
        issue_descriptions = tag.get("issue_descriptions") or {}

        for symptom in symptoms:
            issue_desc = (issue_descriptions.get(symptom) or "").strip() if isinstance(issue_descriptions, dict) else ""
            rows.append({
                "post_id": post_id,
                "subreddit": post.get("subreddit") or "",
                "created_at_local": post.get("created_at_local") or "",
                "created_date": post.get("created_date") or "",
                "created_month": post.get("created_month") or "",
                "title": (post.get("title") or "")[:500],
                "url": post.get("url") or "",
                "is_modem_issue": tag.get("is_modem_issue", False),
                "severity": tag.get("severity") or "low",
                "symptom": symptom,
                "issue_description": issue_desc[:500],
                "connectivity_type": tag.get("connectivity_type") or "unknown",
                "after_update": tag.get("after_update") or "unknown",
                "carrier": tag.get("carrier") or "unknown",
                "device": tag.get("device") or "unknown",
                "evidence_1": e1,
                "evidence_2": e2,
                "evidence_3": e3,
            })
    return rows


def build_issue_summary(long_rows: list[dict]) -> list[dict]:
    """
    Aggregate by symptom: n_posts, n_high, and up to 5 example issue_descriptions
    so output shows which issues are most common and what each issue means.
    """
    modem_rows = [r for r in long_rows if r.get("is_modem_issue") and (r.get("symptom") or "") != "none"]
    # symptom -> (set of post_id, set of post_id with high severity, list of unique descriptions)
    groups = defaultdict(lambda: (set(), set(), []))
    for r in modem_rows:
        symptom = r.get("symptom") or ""
        desc = (r.get("issue_description") or "").strip()
        post_id = r.get("post_id") or ""
        key = symptom
        groups[key][0].add(post_id)
        if (r.get("severity") or "").lower() == "high":
            groups[key][1].add(post_id)
        if desc and desc not in groups[key][2]:
            groups[key][2].append(desc)
    out = []
    for symptom, (post_ids, high_ids, descriptions) in sorted(groups.items(), key=lambda x: -len(x[1][0])):
        d1 = descriptions[0] if len(descriptions) > 0 else ""
        d2 = descriptions[1] if len(descriptions) > 1 else ""
        d3 = descriptions[2] if len(descriptions) > 2 else ""
        d4 = descriptions[3] if len(descriptions) > 3 else ""
        d5 = descriptions[4] if len(descriptions) > 4 else ""
        out.append({
            "symptom": symptom,
            "n_posts": len(post_ids),
            "n_high": len(high_ids),
            "description_1": d1[:400],
            "description_2": d2[:400],
            "description_3": d3[:400],
            "description_4": d4[:400],
            "description_5": d5[:400],
        })
    return out


def build_monthly_counts(long_rows: list[dict]) -> list[dict]:
    """
    Aggregate: (created_month, symptom) -> n_posts (distinct post_id with is_modem_issue),
    n_high (distinct post_id with severity==high).
    """
    # Only rows where is_modem_issue is true
    modem_rows = [r for r in long_rows if r.get("is_modem_issue")]
    # (created_month, symptom) -> (set of post_id, set of post_id with high severity)
    groups = defaultdict(lambda: (set(), set()))
    for r in modem_rows:
        month = r.get("created_month") or ""
        symptom = r.get("symptom") or "none"
        key = (month, symptom)
        post_id = r.get("post_id") or ""
        groups[key][0].add(post_id)
        if (r.get("severity") or "").lower() == "high":
            groups[key][1].add(post_id)

    out = []
    for (created_month, symptom), (post_ids, high_ids) in sorted(groups.items()):
        out.append({
            "created_month": created_month,
            "symptom": symptom,
            "n_posts": len(post_ids),
            "n_high": len(high_ids),
        })
    return out


def main() -> None:
    root = project_root()
    log = get_logger("build_csv_long")

    posts_path = root / "data" / "parsed" / "posts.jsonl"
    tags_path = root / "data" / "llm" / "modem_tags.jsonl"
    out_dir = root / "data" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    long_path = out_dir / "posts_modem_long.csv"
    monthly_path = out_dir / "modem_monthly_counts.csv"

    posts = load_posts(posts_path)
    tags = load_tags(tags_path)
    if not tags:
        log.warning("No modem tags found at %s", tags_path)
        with open(long_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=LONG_COLUMNS)
            w.writeheader()
        with open(monthly_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["created_month", "symptom", "n_posts", "n_high"])
            w.writeheader()
        print("No tags to join. Wrote empty CSVs.")
        return

    long_rows = build_long_rows(posts, tags)
    monthly_rows = build_monthly_counts(long_rows)
    issue_summary_rows = build_issue_summary(long_rows)

    with open(long_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LONG_COLUMNS)
        w.writeheader()
        w.writerows(long_rows)

    with open(monthly_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["created_month", "symptom", "n_posts", "n_high"])
        w.writeheader()
        w.writerows(monthly_rows)

    summary_path = out_dir / "modem_issue_summary.csv"
    summary_cols = ["symptom", "n_posts", "n_high", "description_1", "description_2", "description_3", "description_4", "description_5"]
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=summary_cols)
        w.writeheader()
        w.writerows(issue_summary_rows)

    report_path = out_dir / "modem_issues_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("=== Modem issue summary (for next model improvement) ===\n\n")
        total_posts = len({r["post_id"] for r in long_rows if r.get("is_modem_issue")})
        f.write("Total posts with modem issues: %d\n\n" % total_posts)
        for row in issue_summary_rows:
            f.write("--- %s (n_posts=%d, n_high=%d) ---\n" % (row["symptom"], row["n_posts"], row["n_high"]))
            for i, key in enumerate(["description_1", "description_2", "description_3", "description_4", "description_5"], 1):
                d = (row.get(key) or "").strip()
                if d:
                    f.write("  %d. %s\n" % (i, d))
            f.write("\n")
    log.info("Wrote issue summary: %s", summary_path)
    log.info("Wrote report: %s", report_path)

    print("Wrote %s (%d rows), %s (%d rows), %s (%d rows), and %s." % (
        long_path.name, len(long_rows), monthly_path.name, len(monthly_rows),
        summary_path.name, len(issue_summary_rows), report_path.name))


if __name__ == "__main__":
    main()
