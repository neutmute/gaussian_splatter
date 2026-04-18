# Step 1 -- Frame Extraction
# Extracts frames from an MP4 file or a folder of MP4s into the project's frames\ folder.
# The project name and output path are inferred from the MP4 location:
#   projects\<name>\footage\clip.mp4  ->  frames written to  projects\<name>\frames\
#
# Usage: .\01-ffmpeg.ps1 -Mp4 <path> [-Fps 2] [-Quality 2] [-BeginTime H:MM:SS] [-EndTime H:MM:SS] [-DryRun]

param(
    [Parameter(Mandatory)]
    [string]$Mp4,              # path to a single MP4/MOV file, or a folder containing them
    [int]$Fps        = 2,      # fps to extract (default 2; use 3-4 for fast movement)
    [int]$Quality    = 2,      # JPEG quality: 1 (best) to 5 (worst)
    [string]$BeginTime = "",   # optional start timestamp e.g. 2:03:16 or 00:02:03
    [string]$EndTime   = "",   # optional end timestamp e.g. 2:13:16 or 00:12:13
    [switch]$DryRun            # print commands without running ffmpeg
)

# Parse a timestamp string (H:MM:SS, HH:MM:SS, M:SS, or plain seconds) into total seconds
function ConvertTo-Seconds([string]$ts) {
    if ($ts -match '^(\d+):(\d{2}):(\d{2})$') {
        return [int]$matches[1] * 3600 + [int]$matches[2] * 60 + [int]$matches[3]
    } elseif ($ts -match '^(\d+):(\d{2})$') {
        return [int]$matches[1] * 60 + [int]$matches[2]
    } elseif ($ts -match '^\d+$') {
        return [int]$ts
    } else {
        Write-Error "Cannot parse timestamp '$ts'. Use H:MM:SS, MM:SS, or plain seconds."
        exit 1
    }
}

# Infer the project root by walking up the path looking for a 'footage' folder.
# projects\<name>\footage\clip.mp4  ->  projects\<name>
# Falls back to the folder containing the clips if no 'footage' ancestor is found.
function Get-ProjectDir([string]$path) {
    $item = Get-Item $path -ErrorAction Stop
    $dir  = if ($item.PSIsContainer) { $item } else { $item.Directory }
    $current = $dir
    while ($null -ne $current) {
        if ($current.Name -ieq 'footage') {
            return $current.Parent.FullName
        }
        $current = $current.Parent
    }
    return $dir.FullName
}

# Resolve input clips
$inputItem = Get-Item $Mp4 -ErrorAction Stop
if ($inputItem.PSIsContainer) {
    $clips = Get-ChildItem -Path $inputItem.FullName -Include "*.mp4","*.MP4","*.mov","*.MOV" -Recurse | Sort-Object Name
} else {
    $clips = @($inputItem)
}
if ($clips.Count -eq 0) {
    Write-Error "No MP4/MOV files found at: $Mp4"
    exit 1
}

# Infer project dir and frames output folder
$projectDir  = Get-ProjectDir $Mp4
$projectName = Split-Path $projectDir -Leaf
$FramesDir   = Join-Path $projectDir "frames"

# Validate ffmpeg
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Error "ffmpeg not found on PATH. Install from https://ffmpeg.org/download.html"
    exit 1
}

# Parse optional time range
$beginSec = $null
$endSec   = $null
if ($BeginTime -ne "") { $beginSec = ConvertTo-Seconds $BeginTime }
if ($EndTime   -ne "") { $endSec   = ConvertTo-Seconds $EndTime   }
if ($null -ne $beginSec -and $null -ne $endSec -and $endSec -le $beginSec) {
    Write-Error "-EndTime must be after -BeginTime"
    exit 1
}

# Estimate total frame count and warn if over threshold
$totalDurationSec = 0
foreach ($clip in $clips) {
    $probe = ffprobe -v error -select_streams v:0 -show_entries stream=duration -of csv=p=0 $clip.FullName 2>&1
    if ($probe -match '[\d.]+') {
        $clipDur = [double]$matches[0]
        if ($null -ne $beginSec) { $clipDur -= $beginSec }
        if ($null -ne $endSec)   { $startOffset = if ($null -ne $beginSec) { $beginSec } else { 0 }; $clipDur = [Math]::Min($clipDur, $endSec - $startOffset) }
        if ($clipDur -gt 0) { $totalDurationSec += $clipDur }
    }
}
$estimatedFrames = [int]($totalDurationSec * $Fps)

Write-Host ""
Write-Host "Project     : $projectName"
Write-Host "Clips found : $($clips.Count)"
Write-Host "Extract rate: $Fps fps  |  JPEG quality: $Quality"
if ($null -ne $beginSec -or $null -ne $endSec) {
    $rangeStr = "$(if ($BeginTime) { $BeginTime } else { 'start' }) -> $(if ($EndTime) { $EndTime } else { 'end' })"
    Write-Host "Time range  : $rangeStr"
}
Write-Host "Est. frames : ~$estimatedFrames"
Write-Host "Output dir  : $FramesDir"
if ($estimatedFrames -gt 1000) {
    Write-Warning "Estimated frame count exceeds 1000. Consider lowering -Fps (e.g. -Fps 1) to reduce COLMAP workload."
}
Write-Host ""

# Create output folder; prompt before overwriting existing frames
if (Test-Path $FramesDir) {
    $existing = (Get-ChildItem -Path $FramesDir -Filter "*.jpg" | Measure-Object).Count
    if ($existing -gt 0) {
        $answer = Read-Host "$existing frames already exist in frames\. Overwrite? [y/N]"
        if ($answer -notmatch '^[Yy]') {
            Write-Host "Skipping extraction -- existing frames kept."
            exit 0
        }
        Remove-Item -Path "$FramesDir\*.jpg" -Force
    }
} else {
    if (-not $DryRun) { New-Item -ItemType Directory -Path $FramesDir | Out-Null }
}

# Process each clip — frames written with a per-clip prefix to avoid collisions during extraction
$clipIndex   = 0
$totalFrames = 0

foreach ($clip in $clips) {
    $clipIndex++
    Write-Host "[$clipIndex/$($clips.Count)] $($clip.Name)"

    # Temporary per-clip prefix; frames are renumbered into a single sequence after all clips
    $prefix     = "clip{0:D2}_frame_" -f $clipIndex
    $outPattern = Join-Path $FramesDir ($prefix + "%04d.jpg")

    $ffmpegArgs = @()
    if ($null -ne $beginSec) { $ffmpegArgs += @("-ss", $beginSec) }
    $ffmpegArgs += @("-i", $clip.FullName)
    if ($null -ne $endSec)   { $ffmpegArgs += @("-to", $endSec) }
    $ffmpegArgs += @(
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
    # Renumber all per-clip frames into a single contiguous sequence (frame_0001.jpg, frame_0002.jpg, ...)
    # sorted by clip index then frame number so the chronological order is preserved.
    # This avoids filename gaps at clip boundaries that would break COLMAP's sequential matcher.
    Write-Host "Renumbering frames into a single sequence..."
    $allFrames = Get-ChildItem -Path $FramesDir -Filter "clip*_frame_*.jpg" | Sort-Object Name
    $seq = 1
    foreach ($f in $allFrames) {
        $newName = "frame_{0:D4}.jpg" -f $seq
        Rename-Item -Path $f.FullName -NewName $newName
        $seq++
    }
    Write-Host "Done. $($clips.Count) clips -> $totalFrames frames in $FramesDir"
    Write-Host "Next step: python scripts\02_cull_frames.py projects\$projectName\frames"
}
