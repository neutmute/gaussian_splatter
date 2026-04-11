# 00-install-prereqs.ps1 -- Install all dependencies for the Gaussian Splat pipeline
# Run once before using any of the pipeline scripts.
#
# IMPORTANT: Run this from a "Developer Command Prompt for VS 2022"
#            (or call vcvars64.bat first) so cl.exe is available for CUDA compilation.
#
# Usage:
#   .\scripts\00-install-prereqs.ps1
#   .\scripts\00-install-prereqs.ps1 -GsplatPath C:\apps\gsplat
#
# What this installs:
#   1. PyTorch with the right CUDA build for your GPU (auto-detected)
#   2. Pipeline script dependencies (opencv, numpy, tqdm, etc.)
#   3. gsplat repo + examples dependencies
#      - Clones https://github.com/nerfstudio-project/gsplat if not present
#      - Builds with DISTUTILS_USE_SDK=1 pip install .
#      - Applies the Windows pycolmap binary-parsing fix

param(
    [string]$GsplatPath = "C:\apps\gsplat"
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
    Write-Error "Python not found on PATH. Install Python 3.10 from https://python.org"
    exit 1
}
$pyVer = python --version 2>&1
Write-Host "Python : $pyVer"
if ($pyVer -notmatch "3\.(9|10|11)") {
    Write-Warning "  gsplat is tested on Python 3.9-3.11. Python 3.10 is recommended."
    Write-Warning "  Your version ($pyVer) may cause issues."
}
Write-Host ""

# ---------------------------------------------------------------------------
# 1. PyTorch -- auto-select CUDA build based on GPU compute capability
#    sm_120 = Blackwell (RTX 50xx) -> cu128 / PyTorch 2.7+
#    sm_89+ = Ada/Hopper (RTX 40xx, H100) -> cu121
#    older  -> cu118 safe default
# ---------------------------------------------------------------------------
Write-Host "=== Step 1/3: PyTorch (CUDA auto-detected) ===" -ForegroundColor Cyan

$cudaTag = "cu118"   # safe fallback
$gpuCapRaw = python -c "import subprocess; r=subprocess.run(['nvidia-smi','--query-gpu=compute_cap','--format=csv,noheader'],capture_output=True,text=True); print(r.stdout.strip())" 2>&1
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
} else {
    Write-Warning "  Could not detect GPU compute capability -- defaulting to cu118."
}
$torchIndexUrl = "https://download.pytorch.org/whl/$cudaTag"

$torchCheck = python -c "import torch; print(torch.__version__, torch.cuda.is_available())" 2>&1
$torchInstalled = ($LASTEXITCODE -eq 0)
$torchHasCuda   = ($torchInstalled -and ($torchCheck -match "True$"))

# Check for GPU compatibility warnings (wrong CUDA build for this GPU architecture)
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
        Run-Pip @("uninstall", "torch", "torchvision", "torchaudio", "-y")
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
# 3. gsplat repo
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "=== Step 3/3: gsplat repo ===" -ForegroundColor Cyan

# Clone if not present
if (-not (Test-Path $GsplatPath)) {
    Write-Host "  Cloning gsplat to $GsplatPath ..."
    git clone --recursive https://github.com/nerfstudio-project/gsplat.git $GsplatPath
    if ($LASTEXITCODE -ne 0) {
        Write-Error "  git clone failed. Ensure git is on PATH and you have internet access."
        exit 1
    }
} else {
    Write-Host "  gsplat found at $GsplatPath"
}

# Check nvcc is present and warn if version is too old for this GPU
if (Check-Command "nvcc") {
    $nvccOut = (nvcc --version 2>&1) -join " "
    if ($nvccOut -match "release (\d+)\.(\d+)") {
        $nvccMaj = [int]$Matches[1]; $nvccMin = [int]$Matches[2]
        Write-Host "  nvcc version: $nvccMaj.$nvccMin"

        $gpuName = (nvidia-smi --query-gpu=name --format=csv,noheader 2>&1) | Select-Object -First 1
        if ($gpuName -match "RTX\s*50\d\d" -and ($nvccMaj -lt 12 -or ($nvccMaj -eq 12 -and $nvccMin -lt 8))) {
            Write-Warning ""
            Write-Warning "  *** BLACKWELL GPU DETECTED: $gpuName ***"
            Write-Warning "  nvcc $nvccMaj.$nvccMin found -- Blackwell (sm_120) requires CUDA Toolkit 12.8+."
            Write-Warning "  gsplat CUDA build will likely fail."
            Write-Warning "  Install CUDA Toolkit 12.8: https://developer.nvidia.com/cuda-downloads"
            Write-Warning ""
        }
    }
} else {
    Write-Warning "  nvcc not found on PATH -- CUDA Toolkit may not be installed."
    Write-Warning "  gsplat requires nvcc to build its CUDA kernels."
    Write-Warning "  Install CUDA Toolkit 12.8: https://developer.nvidia.com/cuda-downloads"
}

# DISTUTILS_USE_SDK=1 is required on Windows to use the MSVC compiler from VS Build Tools
# without it, setuptools falls back to MinGW which cannot link CUDA code
Write-Host "  Building gsplat (DISTUTILS_USE_SDK=1 pip install .) ..."
$env:DISTUTILS_USE_SDK = "1"
python -m pip install $GsplatPath
if ($LASTEXITCODE -ne 0) {
    Write-Warning "  gsplat build failed."
    Write-Warning "  Ensure you are running from a Developer Command Prompt for VS 2022"
    Write-Warning "  (or have called vcvars64.bat) so cl.exe is available."
    Write-Warning "  Also verify CUDA Toolkit is installed and nvcc is on PATH."
} else {
    Write-Host "  [OK] gsplat installed."
}

# Install gsplat examples dependencies
$examplesReqs = Join-Path $GsplatPath "examples\requirements.txt"
if (Test-Path $examplesReqs) {
    Write-Host "  Installing gsplat examples requirements..."
    Run-Pip @("install", "-r", $examplesReqs)
} else {
    Write-Warning "  examples/requirements.txt not found at $examplesReqs"
}

# Apply the Windows pycolmap binary-parsing fix
# Stock pycolmap uses struct.unpack('L', f.read(8)) which unpacks only 4 bytes on Windows
# (C 'long' is 32-bit on MSVC) but COLMAP writes 64-bit counts.
# The mathijshenquet fork fixes this with explicit uint64 unpacking.
Write-Host "  Applying pycolmap Windows fix (mathijshenquet fork)..."
python -m pip uninstall pycolmap -y 2>&1 | Out-Null
python -m pip install "git+https://github.com/mathijshenquet/pycolmap"
if ($LASTEXITCODE -ne 0) {
    Write-Warning "  pycolmap fix failed -- you may hit a binary-parsing error during training."
    Write-Warning "  Manual fix: pip install git+https://github.com/mathijshenquet/pycolmap"
} else {
    Write-Host "  [OK] pycolmap (Windows fix) installed."
}

# ---------------------------------------------------------------------------
# PATH check
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "=== PATH check ===" -ForegroundColor Cyan
foreach ($tool in @("ffmpeg", "ffprobe", "colmap", "nvcc")) {
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
Write-Host "If gsplat build failed, ensure:"
Write-Host "  1. You ran this from a Developer Command Prompt for VS 2022"
Write-Host "  2. CUDA Toolkit 12.8 is installed: https://developer.nvidia.com/cuda-downloads"
Write-Host "  3. nvcc is on PATH (check: nvcc --version)"
