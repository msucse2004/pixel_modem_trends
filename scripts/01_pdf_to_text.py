"""
Step 1: Extract text from all PDFs in data/pdfs, one .txt per PDF in data/text.
Uses pdfplumber; preserves page boundaries with ===PAGE i/n=== markers.
"""
import logging
import sys
import warnings
from pathlib import Path

# FontBBox 경고(브라우저 저장 PDF 등에서 흔함) 숨김
warnings.filterwarnings("ignore", message=".*FontBBox.*")
for _log in ("pdfminer", "pdfminer.pdffont"):
    logging.getLogger(_log).setLevel(logging.ERROR)

import pdfplumber

from _utils import get_logger, iter_pdf_files, project_root


def main() -> None:
    root = project_root()
    input_dir = root / "data" / "pdfs"
    output_dir = root / "data" / "text"
    output_dir.mkdir(parents=True, exist_ok=True)

    log = get_logger("pdf_to_text")
    pdfs = iter_pdf_files(input_dir)
    if not pdfs:
        log.warning("No PDFs found in %s", input_dir)
        print("\nSummary: 0 PDFs processed, 0 failed.")
        return

    processed = 0
    failed = 0

    for pdf_path in pdfs:
        out_path = output_dir / (pdf_path.stem + ".txt")
        try:
            with pdfplumber.open(pdf_path) as pdf:
                n = len(pdf.pages)
                parts = []
                page_failures = 0
                for i, page in enumerate(pdf.pages, start=1):
                    try:
                        text = page.extract_text()
                        if text is None:
                            text = ""
                        parts.append(f"\n\n===PAGE {i}/{n}===\n\n{text}")
                    except Exception as e:
                        log.exception("Failed to extract page: file=%s page=%s", pdf_path.name, i)
                        page_failures += 1
                        parts.append(f"\n\n===PAGE {i}/{n}===\n\n[EXTRACTION FAILED: {e}]\n")

                out_path.write_text("".join(parts).lstrip(), encoding="utf-8")
                processed += 1
                log.info("Wrote %s (%d pages)%s", out_path.name, n, " (some pages failed)" if page_failures else "")

        except Exception as e:
            log.exception("Failed to process PDF: %s", pdf_path.name)
            failed += 1
            continue

    print("\nSummary: %d PDFs processed, %d failed." % (processed, failed))
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
