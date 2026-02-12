"""
Step 2: Parse extracted TXT files (from Reddit PDFs) into post-level JSONL.
Uses reddit URL as primary anchor; extracts body/comments and removes noise.
"""
import csv
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    _TZ_SEOUL = ZoneInfo("Asia/Seoul")
except Exception:
    _TZ_SEOUL = timezone(timedelta(hours=9))

from _utils import get_logger, iter_txt_files, project_root

# Reddit post URL: https://www.reddit.com/r/Subreddit/comments/<id>/<slug>/
REDDIT_URL_RE = re.compile(
    r"https://www\.reddit\.com/r/([^/\s]+)/comments/([a-zA-Z0-9]+)/[^\s]*"
)
# Korean footer date: "26. 2. 9. 오전 11:32" or "26.2.9 오후 12:11"
# AM/PM: non-digit run (오전/오후) so we don't consume the hour
KOREAN_DATETIME_RE = re.compile(
    r"(\d{2,4})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})\s*\.?\s*([^\d]+?)\s*(\d{1,2}):(\d{2})"
)
# Relative time in Korean (fallback)
RELATIVE_TIME_RE = re.compile(
    r"r/[^\s]+\s*[•·]\s*(.+?)(?:\n|$)"
)

NOISE_NAV = ("로그인", "메인 콘텐츠로 바로가기")
AD_MARKERS = ("홍보 광고", "더 알아보기")
SEP_BODY_COMMENTS = ("댓글", "답글", "Comment", "Comments")


def find_first_reddit_url(text: str) -> tuple[str, str, str] | None:
    """Return (url, post_id, subreddit) for first reddit post URL, else None."""
    m = REDDIT_URL_RE.search(text)
    if not m:
        return None
    subreddit, post_id = m.group(1), m.group(2)
    url = m.group(0).split()[0] if m.group(0).split() else m.group(0)
    return (url, post_id, subreddit)


def parse_korean_datetime(line: str) -> datetime | None:
    """Parse Korean footer datetime (e.g. '26. 2. 9. 오전 11:32') to Asia/Seoul datetime."""
    m = KOREAN_DATETIME_RE.search(line)
    if not m:
        return None
    y, mo, d, ampm, h, mi = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5), m.group(6)
    year = int(y)
    if year < 100:
        year += 2000
    month, day = int(mo), int(d)
    hour, minute = int(h), int(mi)
    # 오후=U+D6C4(후), 오전=U+C804(전)
    if "\uD6C4" in ampm and hour != 12:
        hour += 12
    elif "\uC804" in ampm and hour == 12:
        hour = 0
    try:
        return datetime(year, month, day, hour, minute, 0, tzinfo=_TZ_SEOUL)
    except Exception:
        return None


def extract_relative_time(text: str) -> str | None:
    """Extract relative time from 'r/subreddit • 1개월 전' style line."""
    m = RELATIVE_TIME_RE.search(text)
    return m.group(1).strip() if m else None


def parse_relative_ago(relative_str: str) -> tuple[int, int, int] | None:
    """
    Parse relative time string to (years, months, days) to subtract from capture date.
    Korean: N년 전, N개월 전, N일 전, N주 전, N시간 전, N분 전, 방금
    English: N year(s) ago, N mo ago, N d ago, N h ago, N min ago, N days ago, etc.
    Returns (years, months, days) or None if unparseable.
    """
    if not relative_str or not relative_str.strip():
        return None
    s = relative_str.strip()
    # Strip leading bullet/space that may come from "r/sub • 1년 전"
    s = re.sub(r"^[\s\u2022\u00b7\u30fb·]+\s*", "", s).strip()
    s_lower = s.lower()

    # Korean (년 = year, 개월 = months, 일 = day, 주 = week)
    m = re.search(r"(\d+)\s*년\s*전", s)
    if m:
        return (int(m.group(1)), 0, 0)
    m = re.search(r"(\d+)\s*개월\s*전", s)
    if m:
        return (0, int(m.group(1)), 0)
    m = re.search(r"(\d+)\s*일\s*전", s)
    if m:
        return (0, 0, int(m.group(1)))
    m = re.search(r"(\d+)\s*주\s*전", s)
    if m:
        return (0, 0, 7 * int(m.group(1)))
    m = re.search(r"(\d+)\s*시간\s*전", s)
    if m:
        return (0, 0, max(0, (int(m.group(1)) + 11) // 24))
    m = re.search(r"(\d+)\s*분\s*전", s)
    if m:
        return (0, 0, 0)
    if "방금" in s:
        return (0, 0, 0)

    # English
    m = re.search(r"(\d+)\s*year", s_lower)
    if m:
        return (int(m.group(1)), 0, 0)
    m = re.search(r"(\d+)\s*mo", s_lower)
    if m:
        return (0, int(m.group(1)), 0)
    m = re.search(r"(\d+)\s*d\s*ago", s_lower)
    if m:
        return (0, 0, int(m.group(1)))
    m = re.search(r"(\d+)\s*day", s_lower)
    if m:
        return (0, 0, int(m.group(1)))
    m = re.search(r"(\d+)\s*h\s*ago", s_lower)
    if m:
        return (0, 0, max(0, (int(m.group(1)) + 11) // 24))
    m = re.search(r"(\d+)\s*month", s_lower)
    if m:
        return (0, int(m.group(1)), 0)
    # Fallback: digit + unit character(s) + 전 (유니코드 차이 대비)
    m = re.search(r"(\d+)\s*년", s)
    if m and "전" in s:
        return (int(m.group(1)), 0, 0)
    m = re.search(r"(\d+)\s*개월", s)
    if m and "전" in s:
        return (0, int(m.group(1)), 0)
    m = re.search(r"(\d+)\s*일", s)
    if m and "전" in s:
        return (0, 0, int(m.group(1)))
    # Very permissive: (\d+)(non-digits)전 then infer from common chars
    m = re.search(r"(\d+)\s*[^\d\s]+\s*전", s)
    if m:
        n = int(m.group(1))
        if "\uac1c\uc6d4" in s or "개월" in s:
            return (0, n, 0)
        if "\uc77c" in s or "일" in s:
            return (0, 0, n)
        if "\ub144" in s or "년" in s:
            return (n, 0, 0)
    return None


def subtract_relative(capture_dt: datetime, years: int, months: int, days: int) -> datetime:
    """Subtract years, months, days from capture_dt (date part). Time is kept from capture."""
    from calendar import monthrange
    y, m, d = capture_dt.year, capture_dt.month, capture_dt.day
    d -= days
    while d <= 0:
        m -= 1
        if m <= 0:
            m += 12
            y -= 1
        d += monthrange(y, m)[1]
    m -= months
    while m <= 0:
        m += 12
        y -= 1
    y -= years
    _, last = monthrange(y, m)
    d = min(d, last)
    try:
        return capture_dt.replace(year=y, month=m, day=d)
    except ValueError:
        return capture_dt.replace(year=y, month=m, day=1)


def extract_title_from_footer(line: str, subreddit: str) -> str | None:
    """Footer format: '26. 2. 9. 오전 11:32 <Title> : r/GooglePixel'. Extract <Title>."""
    # After the time part, take everything before " : r/subreddit"
    pattern = re.compile(r"오[전후]\s*\d{1,2}:\d{2}\s+(.+?)\s*:\s*r/" + re.escape(subreddit), re.DOTALL)
    m = pattern.search(line)
    return m.group(1).strip() if m else None


def extract_title_from_doc_top(lines: list[str]) -> str:
    """
    본문 제일 위에 나온 문장을 타이틀로 사용.
    Skip: empty, footer (Korean datetime), nav, "r/sub • time", author (short single token), URL.
    """
    for line in lines:
        s = line.strip()
        if not s or len(s) < 5:
            continue
        if re.match(r"^===PAGE \d+/\d+===$", s):
            continue
        if KOREAN_DATETIME_RE.search(s):
            continue
        if s in NOISE_NAV or any(m in s for m in AD_MARKERS):
            continue
        if s.startswith("r/") or re.match(r"r/\S+\s*[•·]\s*", s):
            continue
        if REDDIT_URL_RE.search(s):
            continue
        if re.match(r"^[\w\-_]+$", s) and len(s) < 25:
            continue
        if re.match(r"^\d+\s*\d*\s*공유", s):
            continue
        return s[:500]
    return ""


def remove_noise(text: str) -> str:
    """Remove ad blocks, related-posts lists, and nav lines."""
    lines = text.split("\n")
    out = []
    in_ad = False
    for line in lines:
        stripped = line.strip()
        if any(m in line for m in AD_MARKERS):
            in_ad = True
            continue
        if in_ad:
            # Skip until we're past blank/next section
            if stripped and not any(m in line for m in AD_MARKERS):
                in_ad = False
            else:
                continue
        if stripped in NOISE_NAV:
            continue
        # Heuristic: "related posts" – lines that look like "X 좋아요 Y 댓글" in list form (repeated)
        if "좋아요" in line and "댓글" in line and re.search(r"\d+\s*좋아요\s*\d+\s*댓글", line):
            continue
        out.append(line)
    return "\n".join(out)


def split_body_and_comments(cleaned: str, first_url_line: int) -> tuple[str, str]:
    """
    Split cleaned content into body (post) and comments.
    first_url_line: line index where the reddit URL appears (footer); content before that is body+comments.
    Heuristic: first occurrence of 댓글/답글/Comment as section start = comments start.
    """
    lines = cleaned.split("\n")
    body_lines = []
    comment_lines = []
    in_comments = False
    for i, line in enumerate(lines):
        if i >= first_url_line:
            break
        stripped = line.strip()
        if not in_comments and any(sep in stripped for sep in SEP_BODY_COMMENTS):
            # Check it looks like a section header (short line or followed by content)
            if len(stripped) < 80 or stripped in SEP_BODY_COMMENTS:
                in_comments = True
                continue
        if in_comments:
            comment_lines.append(line)
        else:
            body_lines.append(line)
    body_text = "\n".join(body_lines).strip()
    comments_text = "\n".join(comment_lines).strip()
    return body_text, comments_text


def parse_one_txt(txt_path: Path, root: Path) -> dict | None:
    """
    Parse a single TXT file into one post record (first reddit URL only).
    Returns dict with post_id, url, title, subreddit, created_at_local, created_date, created_month,
    source_file, body_text, comments_text, created_relative (if no absolute time), raw_text_cleaned.
    """
    try:
        raw = txt_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return None

    # Remove page markers for parsing (flexible newlines so marker never remains as a line)
    text_no_markers = re.sub(r"\n*===PAGE \d+/\d+===\n*", "\n\n", raw)
    # Normalize CRLF so split("\n") gives clean lines
    text_no_markers = text_no_markers.replace("\r\n", "\n").replace("\r", "\n")

    lines_all = text_no_markers.split("\n")
    url_match = find_first_reddit_url(text_no_markers)
    if not url_match:
        return None
    url, post_id, subreddit = url_match

    source_file = str(txt_path.name)

    # Find line index of the URL (for splitting body/comments before footer)
    url_line_idx = len(lines_all)
    for i, line in enumerate(lines_all):
        if url in line or (f"/comments/{post_id}/" in line and "reddit.com" in line):
            url_line_idx = i
            break

    created_at_local = None
    created_relative = None
    created_date = None
    created_month = None

    # Title: 본문 제일 위 문장 (문서 상단 첫 콘텐츠 줄)
    content_before_footer = lines_all[:url_line_idx] if url_line_idx <= len(lines_all) else lines_all
    title = extract_title_from_doc_top(content_before_footer)
    if not title:
        title = ""

    # 캡처한 날짜(헤더) + "글 올린 날"(상대 시간)으로 작성일 계산
    created_relative = extract_relative_time(text_no_markers) or ""
    capture_dt = None
    # 푸터는 URL 근처에 있으므로 URL 이전 줄들에서 먼저 찾기
    search_lines = lines_all[: min(url_line_idx + 2, len(lines_all))]
    for line in search_lines:
        dt = parse_korean_datetime(line)
        if dt:
            capture_dt = dt
            if not title:
                t = extract_title_from_footer(line, subreddit)
                if t:
                    title = t
            break
    if capture_dt is None:
        for line in lines_all:
            dt = parse_korean_datetime(line)
            if dt:
                capture_dt = dt
                if not title:
                    t = extract_title_from_footer(line, subreddit)
                    if t:
                        title = t
                break

    if capture_dt is not None:
        offset = parse_relative_ago(created_relative) if created_relative else None
        if offset:
            years, months, days = offset
            post_dt = subtract_relative(capture_dt, years, months, days)
            created_at_local = post_dt.isoformat()
            created_date = post_dt.strftime("%Y-%m-%d")
            created_month = post_dt.strftime("%Y-%m")
            created_relative = None
        else:
            created_at_local = capture_dt.isoformat()
            created_date = capture_dt.strftime("%Y-%m-%d")
            created_month = capture_dt.strftime("%Y-%m")
            created_relative = created_relative or None
    else:
        if not created_relative:
            created_relative = ""

    if not title:
        for line in lines_all[:25]:
            line = line.strip()
            if not line or line.startswith("r/") and "•" in line:
                continue
            if REDDIT_URL_RE.search(line):
                continue
            if KOREAN_DATETIME_RE.search(line):
                continue
            title = line[:500]
            break

    cleaned = remove_noise(text_no_markers)
    body_text, comments_text = split_body_and_comments(cleaned, url_line_idx)

    raw_text_cleaned = (body_text + "\n\n" + comments_text).strip()

    return {
        "post_id": post_id,
        "url": url,
        "title": title,
        "subreddit": subreddit,
        "created_at_local": created_at_local,
        "created_date": created_date,
        "created_month": created_month,
        "created_relative": created_relative,
        "source_file": source_file,
        "body_text": body_text,
        "comments_text": comments_text,
        "raw_text_cleaned": raw_text_cleaned,
    }


def main() -> None:
    root = project_root()
    input_dir = root / "data" / "text"
    output_dir = root / "data" / "parsed"
    output_dir.mkdir(parents=True, exist_ok=True)

    log = get_logger("parse_posts")
    txt_files = iter_txt_files(input_dir)
    if not txt_files:
        log.warning("No TXT files found in %s", input_dir)
        (output_dir / "posts.jsonl").write_text("", encoding="utf-8")
        with open(output_dir / "posts_summary.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["post_id", "url", "title", "subreddit", "created_at_local", "created_date", "created_month", "source_file"])
        print("Summary: 0 posts parsed. Wrote empty posts.jsonl and posts_summary.csv.")
        return

    posts = []
    for path in txt_files:
        rec = parse_one_txt(path, root)
        if rec:
            posts.append(rec)
            log.info("Parsed %s -> post_id=%s", path.name, rec["post_id"])
        else:
            log.debug("Skipped (no reddit URL or error): %s", path.name)

    jsonl_path = output_dir / "posts.jsonl"
    csv_path = output_dir / "posts_summary.csv"

    import json
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for rec in posts:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    summary_cols = ["post_id", "url", "title", "subreddit", "created_at_local", "created_date", "created_month", "source_file"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=summary_cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(posts)

    print("\nSummary: %d posts parsed. Wrote %s and %s" % (len(posts), jsonl_path.name, csv_path.name))

    # Sanity check: print first 1-2 records (ensure_ascii=True for Windows console)
    if posts:
        print("\n--- First 1-2 parsed record(s) ---")
        for rec in posts[:2]:
            compact = {k: (v[:80] + "..." if isinstance(v, str) and len(v) > 80 else v) for k, v in rec.items()}
            print(json.dumps(compact, ensure_ascii=True, indent=2))
        print("---")

    if not posts:
        sys.exit(1)


if __name__ == "__main__":
    main()
