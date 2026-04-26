# Step 1 (setup) -- Create Project
# Creates the standard folder structure for a new Gaussian Splat project.
# Usage: .\01-create-project.ps1 -ProjectName <name>
#
# Creates under projects\<ProjectName>\:
#   footage\          <- drop raw MP4s here before running 01-ffmpeg.ps1
#   frames\           <- extracted frames land here
#   frames\culled\    <- frames culled by 02_cull_frames.py
#   images\           <- kept frames; COLMAP input
#   sparse\0\         <- COLMAP sparse model output
#   dense\            <- undistorted output; Lichtfield Studio input (populated by 04_undistort.py)
#   output\ply\       <- reserved for future use

param(
    [Parameter(Mandatory)]
    [string]$ProjectName
)

$ProjectsRoot = Join-Path (Split-Path $PSScriptRoot -Parent) "projects"
$ProjectDir   = Join-Path $ProjectsRoot $ProjectName

if (Test-Path $ProjectDir) {
    Write-Error "Project '$ProjectName' already exists at $ProjectDir"
    exit 1
}

$folders = @(
    "footage",
    "frames",
    "frames\culled",
    "images",
    "sparse\0",
    "dense",
    "output\ply"
)

Write-Host ""
Write-Host "Creating project: $ProjectName"
Write-Host "Location        : $ProjectDir"
Write-Host ""

foreach ($folder in $folders) {
    $path = Join-Path $ProjectDir $folder
    New-Item -ItemType Directory -Path $path | Out-Null
    Write-Host "  + $folder\"
}

Write-Host ""
Write-Host "Done. Next steps:"
Write-Host "  1. Copy raw MP4s into: $ProjectDir\footage\"
Write-Host "  2. Extract frames    : .\scripts\01-ffmpeg.ps1 -ProjectName $ProjectName"
Write-Host "  3. Cull frames       : python scripts\02_cull_frames.py $ProjectName" --auto-cull
Write-Host "  4. Run COLMAP        : python scripts\03_run_colmap.py $ProjectName"
Write-Host "  5. Undistort         : python scripts\04_undistort.py $ProjectName"
Write-Host "  6. Train             : open Lichtfield Studio, load projects\$ProjectName\dense\"
