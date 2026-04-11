# 00-install-prereqs.ps1 -- Install all dependencies for the Gaussian Splat pipeline
# Run once before using any of the pipeline scripts.
#
# Usage:
#   .\scripts\00-install-prereqs.ps1
#   .\scripts\00-install-prereqs.ps1 -RepoPath C:\apps\gaussian-splatting
#
# What this installs:
#   1. PyTorch 2.x with CUDA 11.8  (required by gaussian-splatting train.py)
#   2. Pipeline script dependencies  (opencv, numpy, tqdm, etc.)
#   3. gaussian-splatting repo requirements + submodules  (if repo path is provided)

param(
    [string]$RepoPath = "C:\apps\gaussian-splatting"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
function Check-Command($cmdName) {
    return [bool](Get-Command $cmdName -ErrorAction SilentlyContinue)
}

function Run-Pip($pipArgs) {
    python -m pip $pipArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Error "pip $($pipArgs[0]) failed."
        exit 1
    }
}

# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------
if (-not (Check-Command "python")) {
    Write-Error "Python not found on PATH. Install from https://python.org"
    exit 1
}
Write-Host "Python : $(python --version)"
Write-Host ""

# ---------------------------------------------------------------------------
# 1. PyTorch with CUDA 11.8
#    Must be installed before requirements.txt to avoid pip pulling CPU-only torch
# ---------------------------------------------------------------------------
Write-Host "=== Step 1/3: PyTorch (CUDA) ===" -ForegroundColor Cyan

# Detect GPU compute capability to pick the right CUDA index URL
# sm_120 = Blackwell (RTX 50xx) -- needs cu128 / PyTorch 2.7+
# sm_89  = Ada (RTX 40xx)       -- cu121+ fine
# older                         -- cu118 safe default
$cudaTag = "cu118"   # safe fallback
$gpuCapRaw = python -c "import subprocess,re; r=subprocess.run(['nvidia-smi','--query-gpu=compute_cap','--format=csv,noheader'],capture_output=True,text=True); print(r.stdout.strip())" 2>&1
if ($LASTEXITCODE -eq 0 -and $gpuCapRaw -match "^(\d+)\.(\d+)") {
    $capMajor = [int]$Matches[1]
    $capMinor = [int]$Matches[2]
    if ($capMajor -ge 12) {
        $cudaTag = "cu128"
        Write-Host "  Detected Blackwell GPU (sm_$($capMajor)$($capMinor)) -- using PyTorch + CUDA 12.8"
    } elseif ($capMajor -ge 8 -and $capMinor -ge 9) {
        $cudaTag = "cu121"
        Write-Host "  Detected Ada/Hopper GPU (sm_$($capMajor)$($capMinor)) -- using PyTorch + CUDA 12.1"
    } else {
        Write-Host "  Detected GPU sm_$($capMajor)$($capMinor) -- using PyTorch + CUDA 11.8"
    }
}
$torchIndexUrl = "https://download.pytorch.org/whl/$cudaTag"

$torchCheck = python -c "import torch; print(torch.__version__, torch.cuda.is_available())" 2>&1
$torchInstalled = ($LASTEXITCODE -eq 0)
$torchHasCuda   = ($torchInstalled -and ($torchCheck -match "True$"))

# Also check there are no sm_ compatibility warnings (wrong CUDA build)
$torchCapOk = $true
if ($torchHasCuda) {
    $capWarn = python -c "import warnings, torch; warnings.filterwarnings('error'); torch.cuda.init()" 2>&1
    if ($capWarn -match "not compatible") { $torchCapOk = $false }
}

if ($torchHasCuda -and $torchCapOk) {
    $torchVer = ($torchCheck -replace " True$", "").Trim()
    Write-Host "  [SKIP] PyTorch $torchVer already installed with compatible CUDA support."
} else {
    if ($torchInstalled -and -not $torchCapOk) {
        Write-Warning "  PyTorch found but GPU not compatible with this build -- reinstalling with $cudaTag..."
    } elseif ($torchInstalled) {
        Write-Warning "  PyTorch found but CUDA unavailable -- reinstalling with $cudaTag..."
    } else {
        Write-Host "  Installing PyTorch ($cudaTag)..."
    }
    Run-Pip @("install", "torch", "torchvision", "torchaudio",
              "--index-url", $torchIndexUrl)
}

# ---------------------------------------------------------------------------
# 2. Pipeline script dependencies
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "=== Step 2/3: Pipeline dependencies (requirements.txt) ===" -ForegroundColor Cyan
$reqFile = Join-Path (Split-Path $PSScriptRoot) "requirements.txt"
Run-Pip @("install", "-r", $reqFile)

# ---------------------------------------------------------------------------
# 3. gaussian-splatting repo
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "=== Step 3/3: gaussian-splatting repo dependencies ===" -ForegroundColor Cyan

if (-not (Test-Path $RepoPath)) {
    Write-Warning "  Repo not found at $RepoPath"
    Write-Host "  Clone it first:"
    Write-Host "    git clone https://github.com/graphdeco-inria/gaussian-splatting --recursive $RepoPath"
    Write-Host "  Then re-run: .\scripts\00-install-prereqs.ps1 -RepoPath $RepoPath"
} else {
    Write-Host "  Repo found at $RepoPath"

    $repoReqs = Join-Path $RepoPath "requirements.txt"
    if (Test-Path $repoReqs) {
        Write-Host "  Installing repo requirements..."
        Run-Pip @("install", "-r", $repoReqs)
    }

    # wheel + ninja must be present before building CUDA extensions
    Write-Host "  Installing build tools (wheel, ninja)..."
    python -m pip install wheel ninja
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "  Could not install wheel/ninja -- submodule build may fail."
    }

    # Blackwell GPU check (RTX 5060/5070/5080/5090 etc.) -- needs CUDA 12.8 + PyTorch 2.7+
    $gpuName = (nvidia-smi --query-gpu=name --format=csv,noheader 2>&1) | Select-Object -First 1
    if ($gpuName -match "RTX\s*50\d\d") {
        # Check nvcc version -- must be 12.8+ for sm_120
        $nvccVer = (nvcc --version 2>&1) | Select-String "release (\d+\.\d+)"
        if ($nvccVer -match "release (\d+)\.(\d+)") {
            $nvccMaj = [int]$Matches[1]; $nvccMin = [int]$Matches[2]
            if ($nvccMaj -lt 12 -or ($nvccMaj -eq 12 -and $nvccMin -lt 8)) {
                Write-Warning ""
                Write-Warning "  *** BLACKWELL GPU DETECTED: $gpuName ***"
                Write-Warning "  nvcc $nvccMaj.$nvccMin found -- Blackwell (sm_120) requires CUDA Toolkit 12.8+."
                Write-Warning "  Submodule build will fail or produce broken kernels."
                Write-Warning "  Install CUDA Toolkit 12.8: https://developer.nvidia.com/cuda-downloads"
                Write-Warning ""
            } else {
                Write-Host "  [OK] Blackwell GPU + nvcc $nvccMaj.$nvccMin -- CUDA toolkit compatible."
            }
        } else {
            Write-Warning "  nvcc not found on PATH -- cannot compile CUDA submodules."
            Write-Warning "  Install CUDA Toolkit 12.8: https://developer.nvidia.com/cuda-downloads"
        }
    }

    # Build submodules -- require CUDA toolkit to compile
    foreach ($sub in @("diff-gaussian-rasterization", "simple-knn")) {
        $subPath = Join-Path $RepoPath "submodules\$sub"
        if (Test-Path $subPath) {
            Write-Host "  Building submodule: $sub ..."
            python -m pip install --no-build-isolation $subPath
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "  Submodule $sub failed -- ensure CUDA Toolkit 11.8 is installed and PyTorch is importable (python -c 'import torch')."
            }
        } else {
            Write-Warning "  Submodule not found: $subPath -- did you clone with --recursive?"
        }
    }
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "=== PATH check ===" -ForegroundColor Cyan
foreach ($tool in @("ffmpeg", "ffprobe", "colmap")) {
    if (Check-Command $tool) {
        Write-Host "  [OK]      $tool"
    } else {
        Write-Warning "  [MISSING] $tool -- not found on PATH"
    }
}
if (Check-Command "nvidia-smi") {
    $gpu = (nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>&1) | Select-Object -First 1
    Write-Host "  [OK]      GPU: $gpu"
} else {
    Write-Warning "  [MISSING] nvidia-smi -- NVIDIA drivers may not be installed"
}

Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "If submodules failed, install CUDA Toolkit 11.8 from:"
Write-Host "  https://developer.nvidia.com/cuda-11-8-0-download-archive"
