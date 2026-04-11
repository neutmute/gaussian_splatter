# install-prereqs.ps1 -- Install Python dependencies for the Gaussian Splat pipeline
# Run once before using any of the pipeline scripts.
# Usage: .\install-prereqs.ps1

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python not found on PATH. Install from https://python.org"
    exit 1
}

Write-Host "Python: $(python --version)"

Write-Host "Installing Python packages from requirements.txt..."
python -m pip install -r (Join-Path $PSScriptRoot "requirements.txt")

if ($LASTEXITCODE -ne 0) {
    Write-Error "pip install failed."
    exit 1
}

Write-Host ""
Write-Host "Done. Python dependencies installed."
Write-Host ""
Write-Host "External tools also required (must be installed separately):"
Write-Host "  ffmpeg  -- https://ffmpeg.org/download.html"
Write-Host "  colmap  -- https://colmap.github.io/install.html"
Write-Host "  gaussian-splatting repo -- https://github.com/graphdeco-inria/gaussian-splatting"

# Check which external tools are already on PATH
Write-Host ""
Write-Host "PATH check:"
foreach ($tool in @("ffmpeg", "ffprobe", "colmap")) {
    if (Get-Command $tool -ErrorAction SilentlyContinue) {
        Write-Host "  [OK] $tool found"
    } else {
        Write-Warning "  [MISSING] $tool not found on PATH"
    }
}
