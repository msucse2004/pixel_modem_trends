#!/bin/bash
# Run full pipeline: venv, Python steps 01-05, R charts, then print output paths.
# Run from repo root: ./run_all.sh

set -e
root="$(cd "$(dirname "$0")" && pwd)"
cd "$root"

echo "=== Pixel Modem Trend Pipeline ==="

# 1) Activate .venv if exists
if [ -f ".venv/bin/activate" ]; then
    echo "Activating .venv ..."
    source .venv/bin/activate
else
    echo "No .venv found. Create one with:"
    echo "  python3 -m venv .venv"
    echo "  source .venv/bin/activate"
    echo "  pip install -r requirements.txt"
    echo "Using system Python for now."
fi

# 2) Python scripts 01-05
for step in \
    "01 PDF->text:python scripts/01_pdf_to_text.py" \
    "02 Parse posts:python scripts/02_parse_posts.py" \
    "03 LLM tag modem:python scripts/03_llm_tag_modem.py" \
    "04 Build CSV long:python scripts/04_build_csv_long.py" \
    "05 Copy PDFs by issue:python scripts/05_copy_pdfs_by_issue.py"; do
    name="${step%%:*}"
    cmd="${step#*:}"
    echo ""
    echo "--- $name ---"
    $cmd
done

# 3) R scripts for PNGs
echo ""
echo "--- R: install packages + plot trends ---"
if command -v Rscript &>/dev/null; then
    Rscript r/install_packages.R || true
    Rscript r/plot_trends.R || true
    Rscript r/plot_wordcloud.R || true
else
    echo "Rscript not in PATH. Install R and add to PATH, then run:"
    echo "  Rscript r/install_packages.R"
    echo "  Rscript r/plot_trends.R"
    echo "  Rscript r/plot_wordcloud.R"
fi

# 4) Print final output file paths
echo ""
echo "=== Final output files (data/out) ==="
outDir="$root/data/out"
if [ -d "$outDir" ]; then
    find "$outDir" -maxdepth 1 -type f \( -name "*.png" -o -name "*.pdf" -o -name "*.csv" -o -name "*.txt" \) | sort | while read -r f; do
        echo "  $f"
    done
    byIssue="$outDir/by_issue"
    if [ -d "$byIssue" ]; then
        echo ""
        echo "=== PDFs by issue (data/out/by_issue/*) ==="
        for dir in "$byIssue"/*; do
            [ -d "$dir" ] && echo "  $(basename "$dir"): $(find "$dir" -type f | wc -l) files"
        done
    fi
else
    echo "  (data/out not found)"
fi
echo ""
echo "Done."
