# Gaussian Splat Pipeline — Project Context & Script Briefing

> This file provides context for Claude Code to build reusable scripts for processing
> drone footage into Gaussian Splat scenes using COLMAP + Lichtfield Studio.
> Place this file in your project root: `C:\code\gaussian-splat\CLAUDE.md`
>
> Tutorial reference: https://smartdatascan.com/tutorials/gaussian-splatting-windows/

---

## Project Goal

Build a set of reusable, well-documented Python/shell scripts that automate the full
pipeline from raw drone MP4 footage through to a viewable Gaussian Splat `.ply` file.
Scripts should be modular — each step runnable independently, with clear inputs/outputs
so the user can re-run individual steps without repeating the whole pipeline.

---

## Target Hardware & Environment

- **OS:** Windows (primary), Linux (secondary)
- **GPU:** NVIDIA with CUDA support — RTX 5060 Ti (Blackwell, sm_120) is primary dev GPU
- **CUDA Toolkit:** 12.8+ (required for Blackwell sm_120; 12.6 for Ada/older)
- **Python:** 3.10 recommended
- **Tools required:** FFmpeg, COLMAP v3.11+, Git

---

## Capture Context

Scripts should be optimised for footage captured with these specs:

### Camera: DJI Mini Pro 4
- Resolution: 4K 30fps
- Color profile: D-Log M
- Shutter: 1/60s (fixed, 2× rule)
- ISO: 100 (fixed, sunny conditions)
- White balance: Manual fixed — Cloudy preset (~6200K)
- EIS: OFF (electronic stabilisation must be disabled)
- ND filter: ND16 for sunny morning conditions
- Gimbal: Standard mode

### Shooting Scenarios
1. **House frontage** — simple arc pass at 3–5m + lower pass at 1.5–2m
2. **Garden** — three passes: low through (1–2m), mid orbit (3–5m), high grid (8–15m)
3. **Multiple clips** — different passes extracted into same COLMAP input folder

### Known Capture Issues to Handle
- Parked cars / moving pedestrians between clips → ghost geometry
- Reflective windows → smearing artefacts (known limitation, document don't fix)
- Leaf movement in wind → degrades matching (warn user if many frames are flagged)
- Repetitive facade features → potential COLMAP misregistration

---

## Full Pipeline — Steps & Commands

### Step 0: Install Prerequisites (`00-install-prereqs.ps1`)
Tool: PowerShell + pip

**What it does:**
- Installs pipeline script dependencies from `requirements.txt`
- Checks PATH for required external tools (ffmpeg, colmap)

**Run once before using any pipeline scripts.**

**Example usage:**
```powershell
.\scripts\00-install-prereqs.ps1
```

---

### Step 0.5: Create Project (`01-create-project.ps1`)
Tool: PowerShell

**What it does:**
- Creates the standard folder structure for a new project under `projects\<name>\`
- Run this once before any other step for a new shoot

**Example usage:**
```powershell
.\scripts\01-create-project.ps1 -ProjectName 20260411-house
```

Then copy raw MP4s into `projects\20260411-house\footage\` before proceeding to Step 1.

---

### Step 1: Frame Extraction (`01-ffmpeg.ps1`)
Tool: FFmpeg

**Parameters:**
- `-Mp4` — path to a single MP4/MOV file, or a folder containing them (mandatory)
- `-Fps` — extraction rate (default 2; use 3–4 for fast movement, 1 for slow high passes)
- `-Quality` — JPEG quality 1–5, lower = better (default 2)
- `-BeginTime` — optional start timestamp, e.g. `2:03:16` (H:MM:SS, MM:SS, or seconds)
- `-EndTime` — optional end timestamp, same format
- `-DryRun` — preview ffmpeg commands without writing any files

**Logic:**
- Project name and output folder (`projects\<name>\frames\`) inferred from the `-Mp4` path by locating the `footage` ancestor folder
- Warns if estimated frame count exceeds 1000 (suggest lowering `-Fps`)
- Prefixes frames per clip (`clip01_frame_0001.jpg`) so multi-clip runs don't collide

**Example usage:**
```powershell
# All clips in a footage folder — frames written to projects\20260411-house\frames\
.\scripts\01-ffmpeg.ps1 -Mp4 projects\20260411-house\footage

# Single clip
.\scripts\01-ffmpeg.ps1 -Mp4 projects\20260411-house\footage\DJI_0001.MP4

# Higher frame rate for fast-moving passes
.\scripts\01-ffmpeg.ps1 -Mp4 projects\20260411-house\footage -Fps 4

# Extract a specific time segment (e.g. 10 minutes from a long clip)
.\scripts\01-ffmpeg.ps1 -Mp4 projects\20260411-house\footage\DJI_0001.MP4 -BeginTime 2:03:16 -EndTime 2:13:16

# From a start point to end of clip (e.g. skip shaky first 30 seconds)
.\scripts\01-ffmpeg.ps1 -Mp4 projects\20260411-house\footage\DJI_0001.MP4 -BeginTime 0:00:30

# Dry run — preview ffmpeg commands without extracting anything
.\scripts\01-ffmpeg.ps1 -Mp4 projects\20260411-house\footage\DJI_0001.MP4 -BeginTime 2:03:16 -EndTime 2:13:16 -DryRun
```

---

### Step 2: Frame QC / Cull (`02_cull_frames.py`)
Tool: OpenCV (blur detection via Laplacian variance)

**What it does:**
- Scans extracted frames and scores each for sharpness
- Flags and optionally deletes frames below a blur threshold
- Flags near-duplicate frames (too similar to previous = redundant)
- Produces a report: total frames, flagged frames, recommended culls

**Parameters to expose:**
- Project name (resolves to `projects/<name>/frames/` automatically)
- Blur threshold (default 100 Laplacian variance — tune to footage)
- Similarity threshold for deduplication
- `--dry-run` flag — report only, don't delete
- `--auto-cull` flag — delete flagged frames automatically

**Output:**
- `cull_report.txt` listing flagged files with scores
- Kept frames copied to `projects/<name>/images/` (the COLMAP input folder)
- Flagged frames moved to `projects/<name>/frames/culled/` subfolder

**Example usage (project: 20260411-house):**
```bash
# Dry run first — see what would be flagged without touching anything
python scripts/02_cull_frames.py 20260411-house --dry-run

# Auto-cull flagged frames (moves to frames/culled/, copies kept frames to images/)
python scripts/02_cull_frames.py 20260411-house --auto-cull

# If too many frames flagged, loosen the blur threshold and retry
python scripts/02_cull_frames.py 20260411-house --auto-cull --blur-threshold 60
```

---

### Step 3: COLMAP SfM (`03_run_colmap.py`)
Tool: COLMAP CLI v3.11+

**What it does:**
Runs the COLMAP pipeline headlessly via CLI (no GUI required):
1. Feature extraction (GPU-accelerated)
2. Feature matching  (sequential by default; exhaustive with --exhaustive)
3. Sparse reconstruction (mapper)

Outputs `sparse/0/` only. Run `04_undistort.py` next to produce the `dense/` folder required by Lichtfield Studio.

```bash
# Feature extraction
colmap feature_extractor \
  --database_path project/colmap.db \
  --image_path project/images \
  --ImageReader.camera_model OPENCV \
  --ImageReader.single_camera 1 \
  --SiftExtraction.use_gpu 1

# Sequential matching (default for drone footage)
colmap sequential_matcher \
  --database_path project/colmap.db \
  --SequentialMatching.overlap 15 \
  --SiftMatching.use_gpu 1

# Sparse reconstruction
colmap mapper \
  --database_path project/colmap.db \
  --image_path project/images \
  --output_path project/sparse
```

**Parameters to expose:**
- Project folder path
- Sequential overlap (default 15, increase to 20–30 for tricky footage)
- `--exhaustive` flag — switch to exhaustive matcher (slower, more thorough)
- `--guided-matching` flag — adds geometric constraint filtering (helps difficult scenes)
- `--relaxed` flag — loosens mapper thresholds for scenes that fail to initialise:
  - `--Mapper.init_min_tri_angle 2` (default: 16)
  - `--Mapper.init_min_num_inliers 4` (default: 100)
  - `--Mapper.abs_pose_min_num_inliers 3` (default: 30)
  - `--Mapper.abs_pose_max_error 8` (default: 12)
- `--camera-model` — COLMAP camera model (default: `OPENCV` for standard drone lenses; use `OPENCV_FISHEYE` for fisheye lenses like the DJI Avata 2 with 155° FOV)
- COLMAP binary path (for non-standard installs)

**Output validation:**
- After mapper, read `sparse/0/images.bin` and report: X of Y images registered (%)
- Warn if <70% registered — suggest exhaustive matching or re-culling
- Warn if multiple sparse models produced (fragmentation)

**Example usage (project: 20260411-house):**
```bash
# Standard run — sequential matcher, overlap 15
python scripts/03_run_colmap.py 20260411-house

# If registration is low (<70%) or footage is multi-clip — try exhaustive matcher
python scripts/03_run_colmap.py 20260411-house --exhaustive

# Difficult scene (repetitive facade, tight arc) — exhaustive + guided + relaxed thresholds
python scripts/03_run_colmap.py 20260411-house --exhaustive --guided-matching --relaxed

# Fisheye lens (e.g. DJI Avata 2, 155° FOV) — use OPENCV_FISHEYE camera model
python scripts/03_run_colmap.py 20260411-house --camera-model OPENCV_FISHEYE

# Re-run after failed attempt (auto-deletes stale colmap.db and sparse/)
python scripts/03_run_colmap.py 20260411-house --overwrite
```

---

### Step 4: COLMAP Undistortion (`04_undistort.py`)
Tool: COLMAP CLI (`image_undistorter`)

**What it does:**
Runs `colmap image_undistorter` to produce undistorted images and an undistorted sparse model
in `projects/<name>/dense/`. This is the folder Lichtfield Studio loads directly.

- `--max_image_size 1600` — required by Lichtfield Studio; larger images are downscaled
- `--output_type COLMAP` — outputs a COLMAP-format sparse model alongside the undistorted images

**Parameters:**
- `project_name` — project folder name under `projects\` (e.g. `20260411-house`)
- `--overwrite` — delete existing `dense/` output and re-run

**Output:**
```
projects/<name>/dense/
    images/     ← undistorted images (Lichtfield input)
    sparse/     ← undistorted sparse model (Lichtfield input)
```

**Example usage (project: 20260411-house):**
```bash
# Standard run
python scripts/04_undistort.py 20260411-house

# Re-run after a failed or partial attempt
python scripts/04_undistort.py 20260411-house --overwrite
```

---

### Step 5: Lichtfield Studio (manual)

**What it does:**
Lichtfield Studio is a Windows GUI application for training and viewing Gaussian Splats.
It takes the `dense/` folder produced by Step 4 as input.

**Steps:**
1. Open Lichtfield Studio
2. Load or drop the folder `projects\<name>\dense\` into the application
3. Train from within Lichtfield Studio

Note: Lichtfield Studio has a CLI — a `05_lichtfield.py` script is a future addition.

---

## Suggested Project File Structure

```
C:\code\gaussian-splat\
├── CLAUDE.md                  ← this file
├── scripts\
│   ├── 00-install-prereqs.ps1
│   ├── 01-create-project.ps1
│   ├── 01-ffmpeg.ps1
│   ├── 02_cull_frames.py
│   ├── 03_run_colmap.py
│   └── 04_undistort.py
├── projects\
│   └── house_frontage_01\
│       ├── footage\           ← raw MP4s go here
│       ├── frames\            ← extracted frames (with frames/culled/ subdir)
│       ├── images\            ← culled frames — COLMAP input
│       ├── colmap.db          ← COLMAP database
│       ├── sparse\
│       │   └── 0\             ← sparse model (cameras.bin, images.bin, points3D.bin)
│       └── dense\             ← Lichtfield Studio input (created by 04_undistort.py)
│           ├── images\        ← undistorted images
│           └── sparse\        ← undistorted sparse model
└── requirements.txt
```

`dense/` is populated by `04_undistort.py` (Step 4). Load this folder into Lichtfield Studio to train.

---

## Dependencies (`requirements.txt`)

```
opencv-python
numpy
PyYAML
tqdm
Pillow
```

External tools (must be installed separately):
- `ffmpeg` — on PATH
- `colmap` v3.11+ — on PATH (download Windows ZIP from github.com/colmap/colmap/releases)
- `gsplat` repo — cloned to disk, path passed via --gsplat flag or pipeline_config.yaml
- Microsoft Build Tools for VS 2022 — required to compile gsplat CUDA kernels

---

## Known Gotchas & Troubleshooting Notes

| Issue | Cause | Script Handling |
|---|---|---|
| COLMAP registers <70% images | Blur, low overlap | Warn user, suggest `--exhaustive --guided-matching` |
| Multiple sparse models | Fragmented reconstruction | Detect in output, warn, suggest more overlap in capture |
| VRAM OOM during training | GPU too small | Auto-detect and suggest higher `--data-factor` |
| pycolmap `struct.unpack('L'...)` error | Windows binary parsing bug in stock pycolmap | Warn and print fix command |
| FFmpeg not found | Not on PATH | Clear error message with install instructions |
| Frames folder already exists | Re-run scenario | Ask user to confirm overwrite or skip |
| gsplat build fails | DISTUTILS_USE_SDK not set, or wrong CUDA toolkit | Script sets env var; check nvcc version matches PyTorch CUDA |
| Blackwell GPU not recognised by PyTorch | Wrong PyTorch build (needs cu128) | prereqs script auto-detects sm_120 and installs cu128 build |

---

## PowerShell Scripting Rules

Rules learned from bugs. Follow these in all `.ps1` scripts:

- **Never use `$args` as a parameter name** — it is a reserved automatic variable in PowerShell. Use `$pipArgs`, `$cmdArgs`, etc. instead.
- **Never use `Set-StrictMode -Version Latest` in setup scripts** — it breaks graceful handling of missing tools and causes unexpected parse failures.
- **Never use `2>$null` to capture command output into a variable** — it is unreliable in assignments. Use `2>&1` to merge stderr into stdout, then check `$LASTEXITCODE`.
- **Never use `$ErrorActionPreference = "Stop"` globally** — use `-ErrorAction Stop` on specific cmdlets that should terminate on failure instead.

---

## Viewing Output

- **Browser (easiest):** https://superspl.at/editor — drag `.ply` file in (can also install as PWA)
- **Editing:** SuperSplat supports removing floating artifacts, cropping, merging, and exporting cleaned `.ply` files
- Output `.ply` location: `projects/[name]/output/ply/point_cloud_29999.ply`

---

## Session Notes

- Primary capture hardware: DJI Mini Pro 4
- Secondary scenario discussed: GoPro 9 (use linear mode, EIS off, less ideal)
- Garden shoots require bridging altitude passes to avoid COLMAP fragmentation
- House frontage recommended as first/test project — simpler, more reliable
- Shoot in calm conditions, overcast preferred, early morning minimises traffic/people
- D-Log M footage should be colour-graded before visual review but raw frames
  (ungraded) are fine for COLMAP — it works on luminance/feature geometry not colour
- Dev GPU is RTX 5060 Ti (Blackwell, sm_120) — requires CUDA 12.8 + PyTorch cu128
