# Run full pipeline: venv, Python steps 01-04, R charts, then print output paths.
# Run from repo root: .\run_all.ps1

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
if (-not $root) { $root = Get-Location }
Set-Location $root

Write-Host "=== Pixel Modem Trend Pipeline ===" -ForegroundColor Cyan

# 1) Activate .venv if exists
if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    Write-Host "Activating .venv ..." -ForegroundColor Green
    & .\.venv\Scripts\Activate.ps1
} else {
    Write-Host "No .venv found. Create one with:" -ForegroundColor Yellow
    Write-Host "  python -m venv .venv"
    Write-Host "  .\.venv\Scripts\Activate.ps1"
    Write-Host "  pip install pdfplumber requests"
    Write-Host "Using system Python for now." -ForegroundColor Yellow
}

# 2) Python scripts 01-04 in order
$steps = @(
    @{ name = "01 PDF->text";     cmd = "python scripts/01_pdf_to_text.py" },
    @{ name = "02 Parse posts";   cmd = "python scripts/02_parse_posts.py" },
    @{ name = "03 LLM tag modem"; cmd = "python scripts/03_llm_tag_modem.py" },
    @{ name = "04 Build CSV long"; cmd = "python scripts/04_build_csv_long.py" },
    @{ name = "05 Copy PDFs by issue"; cmd = "python scripts/05_copy_pdfs_by_issue.py" }
)
foreach ($s in $steps) {
    Write-Host "`n--- $($s.name) ---" -ForegroundColor Cyan
    Invoke-Expression $s.cmd
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Step failed with exit code $LASTEXITCODE. Stopping." -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

# 3) R scripts for PNGs (use user library so install works without admin)
$env:R_LIBS_USER = "$env:USERPROFILE\R\win-library\4.5"
Write-Host "`n--- R: install packages + plot trends ---" -ForegroundColor Cyan
$rscript = Get-Command Rscript -ErrorAction SilentlyContinue
if ($rscript) {
    Rscript r/install_packages.R
    if ($LASTEXITCODE -ne 0) { Write-Host "R install_packages failed." -ForegroundColor Yellow }
    Rscript r/plot_trends.R
    if ($LASTEXITCODE -ne 0) { Write-Host "R plot_trends failed." -ForegroundColor Yellow }
    Rscript r/plot_wordcloud.R
    if ($LASTEXITCODE -ne 0) { Write-Host "R plot_wordcloud failed." -ForegroundColor Yellow }
} else {
    Write-Host "Rscript not in PATH. Install R and add to PATH, then run:" -ForegroundColor Yellow
    Write-Host "  Rscript r/install_packages.R"
    Write-Host "  Rscript r/plot_trends.R"
    Write-Host "  Rscript r/plot_wordcloud.R"
}

# 4) Print final output file paths
Write-Host "`n=== Final output files (data\out) ===" -ForegroundColor Cyan
$outDir = Join-Path $root "data\out"
if (Test-Path $outDir) {
    Get-ChildItem $outDir -File | ForEach-Object { Write-Host "  $($_.FullName)" }
    $byIssue = Join-Path $outDir "by_issue"
    if (Test-Path $byIssue) {
        Write-Host "`n=== PDFs by issue (data\out\by_issue\*) ===" -ForegroundColor Cyan
        Get-ChildItem $byIssue -Directory | ForEach-Object { Write-Host "  $($_.Name): $((Get-ChildItem $_.FullName -File).Count) PDFs" }
    }
} else {
    Write-Host "  (data\out not found)" -ForegroundColor Gray
}
Write-Host "`nDone." -ForegroundColor Green
