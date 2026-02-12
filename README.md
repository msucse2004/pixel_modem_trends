# Reddit PDF → 모뎀 이슈 트렌드 차트 파이프라인

수동 저장한 Reddit PDF를 로컬에서만 처리해 모뎀 이슈 트렌드 차트를 만드는 파이프라인입니다. **클라우드 서비스 없음.** Ollama가 이미 설치되어 있다고 가정합니다.

---

## 프로젝트 구조

```
pixel-modem-trend/
├── data/
│   ├── pdfs/      # 수동 저장한 Reddit PDF 원본
│   ├── text/      # PDF에서 추출한 텍스트
│   ├── parsed/    # 파싱된 모뎀 이슈 레코드 (구조화 데이터)
│   ├── llm/       # Ollama로 보강/정규화한 결과
│   └── out/       # 최종 차트·리포트 출력
├── scripts/       # 파이프라인 스크립트 (Python 등)
├── r/             # R 스크립트 (차트 생성용, 선택)
└── README.md
```

---

## 파이프라인 단계 (순서대로)

| 단계 | 설명 | 입력 | 출력 |
|------|------|------|------|
| **1** | Reddit PDF를 `data/pdfs`에 넣기 | (수동) | `data/pdfs/*.pdf` |
| **2** | PDF → 텍스트 추출 | `data/pdfs/` | `data/text/` |
| **3** | 텍스트에서 모뎀 이슈 파싱 (날짜, 모델, 증상 등) | `data/text/` | `data/parsed/` |
| **4** | (선택) Ollama로 엔티티 정규화·분류 | `data/parsed/` | `data/llm/` |
| **5** | 트렌드 집계 및 차트 생성 | `data/parsed/` 또는 `data/llm/` | `data/out/` |

---

## 실행 순서 (실행할 정확한 명령)

아래는 **스크립트가 준비된 후** 프로젝트 루트(`pixel-modem-trend`)에서 실행하는 순서입니다.

1. **PDF 준비**  
   Reddit에서 저장한 PDF 파일을 `data\pdfs` 폴더에 복사합니다.

2. **PDF → 텍스트 추출**
   ```powershell
   python scripts/01_pdf_to_text.py
   ```
   - 입력: `data/pdfs` (모든 `*.pdf`)
   - 출력: `data/text` (PDF당 하나의 `.txt`, 동일한 기본 파일명)
   - 페이지 경계는 `===PAGE {i}/{n}===` 마커로 유지됨.

3. **텍스트 → 게시글 단위 파싱 (JSONL + CSV)**
   ```powershell
   python scripts/02_parse_posts.py
   ```
   - 입력: `data/text` (Step 1에서 추출한 모든 `.txt`)
   - 출력:
     - `data/parsed/posts.jsonl` — 게시글당 한 줄 JSON (post_id, url, title, subreddit, created_*, body_text, comments_text, raw_text_cleaned 등)
     - `data/parsed/posts_summary.csv` — 요약 메타데이터 (post_id, url, title, subreddit, created_at_local, created_date, created_month, source_file)
   - Reddit URL을 앵커로 사용하며, 한 TXT 내 여러 URL이 있으면 첫 번째 Reddit 포스트 URL만 사용. 절대 시간이 없으면 `created_at_local`은 null, `created_relative`에 상대 시간 문자열 저장.
   - 실행 끝에 첫 1~2개 파싱 레코드를 출력해 sanity check.

4. **Ollama로 모뎀 이슈 태깅**
   ```powershell
   python scripts/03_llm_tag_modem.py
   ```
   - 입력: `data/parsed/posts.jsonl`
   - 출력: `data/llm/modem_tags.jsonl` (post_id, is_modem_issue, severity, symptoms, **issue_descriptions**, after_update, carrier, device, evidence)
   - **본문 전체**(최대 5000자)와 모뎀 관련 댓글을 분석해 모뎀 이슈를 최대한 타게팅. 각 증상별로 **issue_descriptions**(유저가 겪는 문제 한 줄 설명) 추출 → 다음 모델 개선용.
   - 옵션: `--model llama3.2:3b`, `--max_posts N`, `--only_subreddits GooglePixel,Pixel6`, **`--retag`** (기존 결과 무시하고 전부 재태깅, issue_descriptions 채우기)
   - 이미 출력에 있는 post_id는 건너뜀 (재개 안전). 프롬프트: `scripts/prompts/modem_prompt.txt`

5. **R용 long CSV 및 이슈 요약 생성**
   ```powershell
   python scripts/04_build_csv_long.py
   ```
   - 입력: `data/parsed/posts.jsonl`, `data/llm/modem_tags.jsonl` (post_id로 조인)
   - 출력:
     - `data/out/posts_modem_long.csv` — long 포맷: (post_id, symptom)당 한 행. 컬럼에 **issue_description**(해당 증상에 대한 한 줄 설명) 포함.
     - `data/out/modem_monthly_counts.csv` — 월별·증상별 집계 (n_posts, n_high)
     - **`data/out/modem_issue_summary.csv`** — 증상별 건수(n_posts, n_high) + 해당 이슈가 **어떤 문제인지** 예시 설명 5개 (description_1~5)
     - **`data/out/modem_issues_report.txt`** — 요약 리포트: 어떤 이슈가 많이 나오는지, 각 이슈가 어떤 문제인지 텍스트로 정리

6. **이슈별 PDF 복사**
   ```powershell
   python scripts/05_copy_pdfs_by_issue.py
   ```
   - 입력: `data/parsed/posts.jsonl`, `data/out/posts_modem_long.csv`
   - 출력: **`data/out/by_issue/{symptom}/`** — `modem_issues_report.txt`에 분류된 각 이슈 이름으로 폴더 생성, 해당 이슈에 해당하는 원본 PDF 복사

7. **R로 트렌드 차트 생성**
   ```powershell
   Rscript r/install_packages.R
   Rscript r/plot_trends.R
   ```
   - 입력: `data/out/posts_modem_long.csv` (Step 4 결과)
   - 출력 (모두 `data/out/`):
     - `modem_trend_monthly.png` — 월별 모뎀 이슈 총건수 (symptom "none" 제외), 선+점
     - `modem_symptoms_monthly.png` — 월별 증상별 추이 (총건수 상위 6개 증상), 증상별 라인
   - 누락 월은 0으로 채움. `created_month`(Asia/Seoul 기준) 사용.
   - 필요 패키지: ggplot2, dplyr, readr, lubridate (`install_packages.R`로 설치)

최종 차트·CSV 등은 `data\out`에서 확인합니다.

---

## 한 번에 실행 (run_all.ps1)

Windows에서 파이프라인 전체를 한 번에 실행:

```powershell
cd c:\workspace\pixel-modem-trend
.\run_all.ps1
```

동작: (1) `.venv`가 있으면 활성화 (2) Python 01→02→03→04→05 순서 실행 (3) R로 패키지 설치 후 차트·워드클라우드 생성 (4) 최종 출력 파일 경로 및 `by_issue` 폴더 요약 출력.

---

## 수동 실행 (Makefile 스타일 명령)

단계별로 복사해 실행할 때 사용. **프로젝트 루트**에서 실행.

| 목적 | 명령 |
|------|------|
| 가상환경 생성 | `python -m venv .venv` |
| 가상환경 활성화 | `.\.venv\Scripts\Activate.ps1` |
| Python 의존성 설치 | `pip install pdfplumber requests` |
| Step 1 (PDF→텍스트) | `python scripts/01_pdf_to_text.py` |
| Step 2 (파싱) | `python scripts/02_parse_posts.py` |
| Step 3 (Ollama 태깅) | `python scripts/03_llm_tag_modem.py` |
| Step 3 (3개만 테스트) | `python scripts/03_llm_tag_modem.py --max_posts 3` |
| Step 4 (long CSV) | `python scripts/04_build_csv_long.py` |
| Step 5 (이슈별 PDF 복사) | `python scripts/05_copy_pdfs_by_issue.py` |
| R 패키지 설치 | `Rscript r/install_packages.R` |
| R 차트 생성 | `Rscript r/plot_trends.R` |
| 출력 파일 확인 | `dir data\out` |

---

## 사전 요구사항 (로컬만)

- **Python 3** (PDF 추출: `pypdf` 또는 `pdfplumber`, 필요 시 `ollama` 클라이언트)
- **Ollama** (이미 설치됨, 로컬 LLM용)
- **(선택) R** + ggplot2 등 (R로 차트 생성할 경우)

---

## 첫 설정 후 실행할 명령 (지금 당장)

프로젝트 구조만 만든 상태에서는 아래만 실행하면 됩니다.

```powershell
cd c:\workspace\pixel-modem-trend
dir data
dir scripts
dir r
```

이후 `scripts/` 안에 나머지 스크립트를 구현하고, PDF를 `data\pdfs`에 넣은 뒤 위 **실행 순서**대로 명령을 실행하면 됩니다.

---

## Step 1 스모크 테스트 (PDF → 텍스트)

PDF가 없어도 스크립트는 정상 종료됩니다. 프로젝트 루트에서:

```powershell
cd c:\workspace\pixel-modem-trend
python scripts/01_pdf_to_text.py
```

**예상 출력 (PDF 없을 때):**
```
WARNING - pdf_to_text - No PDFs found in c:\workspace\pixel-modem-trend\data\pdfs

Summary: 0 PDFs processed, 0 failed.
```

**예상 출력 (PDF 1개 성공 시):**
```
INFO - pdf_to_text - Wrote example.pdf.txt (3 pages)

Summary: 1 PDFs processed, 0 failed.
```

의존성: `pip install pdfplumber`

---

## Step 2 스모크 테스트 (TXT → JSONL/CSV)

TXT가 없거나 Reddit URL이 없어도 스크립트는 동작합니다. Step 1 실행 후:

```powershell
cd c:\workspace\pixel-modem-trend
python scripts/02_parse_posts.py
```

**생성 파일:** `data/parsed/posts.jsonl`, `data/parsed/posts_summary.csv`

**Sanity check:** 스크립트 끝에서 파싱된 레코드 중 첫 1~2개를 출력합니다. 예시:

```text
Summary: 2 posts parsed. Wrote posts.jsonl and posts_summary.csv.

--- First 1-2 parsed record(s) ---
{
  "post_id": "abc123",
  "url": "https://www.reddit.com/r/GooglePixel/comments/abc123/...",
  "title": "Modem keeps dropping",
  "subreddit": "GooglePixel",
  "created_at_local": "2026-02-09T11:32:00+09:00",
  "created_date": "2026-02-09",
  "created_month": "2026-02",
  "source_file": "saved.pdf.txt",
  "body_text": "...",
  "comments_text": "...",
  "raw_text_cleaned": "..."
}
--- 
```

---

## Step 3 테스트 (Ollama 모뎀 태깅)

Ollama가 실행 중이어야 합니다 (`ollama serve` 또는 Ollama 앱 실행). **3개 포스트만** 태깅하고 출력 샘플 확인:

```powershell
cd c:\workspace\pixel-modem-trend
python scripts/03_llm_tag_modem.py --max_posts 3
```

**생성 파일:** `data/llm/modem_tags.jsonl`

**예상 출력:** 처리된 개수와, 이번 실행에서 쓴 마지막 1~2개 레코드가 JSON으로 출력됩니다.

```text
Tagged 3 posts. Output: c:\workspace\pixel-modem-trend\data\llm\modem_tags.jsonl

--- Sample tagged output (last 1-2 in this run) ---
{
  "post_id": "abc123",
  "is_modem_issue": true,
  "severity": "medium",
  "symptoms": ["lost_connectivity", "low_signal"],
  "after_update": "unknown",
  "carrier": "Verizon",
  "device": "Pixel 8",
  "evidence": ["My data drops every day.", "No bars at home."]
}
---
```

의존성: `pip install requests`
