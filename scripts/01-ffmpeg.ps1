# Step 1 -- Frame Extraction
# Extracts frames from all MP4s in ./raw into ./frames
# Usage: .\step1-ffmpeg.ps1 [-Fps 2] [-Quality 2] [-DryRun]

param(
    [int]$Fps     = 2,      # fps to extract (default 2; use 3-4 for fast movement)
    [int]$Quality = 2,      # JPEG quality: 1 (best) to 5 (worst)
    [switch]$DryRun         # print commands without running ffmpeg
)

$RawDir    = Join-Path $PSScriptRoot "raw"
$FramesDir = Join-Path $PSScriptRoot "frames"

# Validate ffmpeg
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Error "ffmpeg not found on PATH. Install from https://ffmpeg.org/download.html"
    exit 1
}

# Find input clips
$clips = Get-ChildItem -Path $RawDir -Include "*.mp4","*.MP4","*.mov","*.MOV" -Recurse
if ($clips.Count -eq 0) {
    Write-Error "No MP4/MOV files found in $RawDir"
    exit 1
}

# Estimate total frame count and warn if over threshold
$totalDurationSec = 0
foreach ($clip in $clips) {
    $probe = ffprobe -v error -select_streams v:0 -show_entries stream=duration -of csv=p=0 $clip.FullName 2>$null
    if ($probe -match '[\d.]+') {
        $totalDurationSec += [double]$matches[0]
    }
}
$estimatedFrames = [int]($totalDurationSec * $Fps)
Write-Host ""
Write-Host "Clips found : $($clips.Count)"
Write-Host "Extract rate: $Fps fps  |  JPEG quality: $Quality"
Write-Host "Est. frames : ~$estimatedFrames"
if ($estimatedFrames -gt 1000) {
    Write-Warning "Estimated frame count exceeds 1000. Consider lowering -Fps (e.g. -Fps 1) to reduce COLMAP workload."
}
Write-Host ""

# Create output folder; prompt before overwriting existing frames
if (Test-Path $FramesDir) {
    $existing = Get-ChildItem -Path $FramesDir -Filter "*.jpg" | Measure-Object
    if ($existing.Count -gt 0) {
        $answer = Read-Host "$($existing.Count) frames already exist in .rames. Overwrite? [y/N]"
        if ($answer -notmatch '^[Yy]') {
            Write-Host "Skipping extraction -- existing frames kept."
            exit 0
        }
        Remove-Item -Path "$FramesDir\*.jpg" -Force
    }
} else {
    if (-not $DryRun) { New-Item -ItemType Directory -Path $FramesDir | Out-Null }
}

# Process each clip
$clipIndex   = 0
$totalFrames = 0

foreach ($clip in $clips) {
    $clipIndex++
    Write-Host "[$clipIndex/$($clips.Count)] $($clip.Name)"

    # Prefix frames with clip number so multi-clip runs don't collide
    $prefix = "clip{0:D2}_frame_" -f $clipIndex
    $outPattern = Join-Path $FramesDir ($prefix + "%04d.jpg")

    $ffmpegArgs = @(
        "-i", $clip.FullName,
        "-vf", "fps=$Fps",
        "-q:v", $Quality,
        $outPattern
    )

    if ($DryRun) {
        Write-Host "  [DRY RUN] ffmpeg $($ffmpegArgs -join ' ')"
    } else {
        & ffmpeg @ffmpegArgs 2>&1 | Where-Object { $_ -match "frame=" -or $_ -match "error" } | Write-Host
        $extracted = (Get-ChildItem -Path $FramesDir -Filter ($prefix + "*.jpg")).Count
        Write-Host "  => $extracted frames extracted"
        $totalFrames += $extracted
    }
}

Write-Host ""
if ($DryRun) {
    Write-Host "[DRY RUN] $($clips.Count) clips would be processed. No files written."
} else {
    Write-Host "Done. $($clips.Count) clips processed, $totalFrames total frames in .rames"
    Write-Host "Next step: run 02_cull_frames.py"
}
